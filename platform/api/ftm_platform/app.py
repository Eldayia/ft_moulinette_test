"""API publique de la plateforme (FastAPI), derrière Nginx Proxy Manager.

Elle authentifie les utilisateurs, valide et empaquette les soumissions, réserve les quotas et met en file.
Elle n'exécute jamais de code soumis et ne détient aucun identifiant Google (seul le worker en a).
"""
import json
import time
import uuid
from collections import Counter
from datetime import timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import delete, func, select

from ft_moulinette_runners.base import PROJECTS, ExecutionError
from ft_moulinette_runners.config import limits_from_env
from ft_moulinette_runners.workspace import archive_digest
from ftm_dispatcher.quotas import QuotaExceeded

from . import __version__, intake
from .db import session_factory, transaction
from .models import FINISHED, ApiToken, Session, Submission, User, now
from .runtime import Runtime
from .security import DUMMY_HASH, generate_password, hash_password, new_token, token_hash, verify_password
from .settings import Settings

COOKIE = 'ftm_session'
CSRF_HEADER = 'x-ftm-csrf'
FORM_MARGIN = 256 * 1024


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def summary_of(submission):
    report = submission.report or {}
    return dict(id=submission.id, project=submission.project, target=submission.target, source=submission.source,
                status=submission.status, outcome=submission.outcome, files=submission.files_count,
                created_at=submission.created_at.isoformat(),
                finished_at=submission.finished_at.isoformat() if submission.finished_at else None,
                duration_seconds=submission.duration_seconds, summary=report.get('summary'),
                error=submission.error)


def create_app(settings=None, runtime=None):
    settings = settings or Settings.from_env()
    runtime = runtime or Runtime(settings.redis_url)
    factory = session_factory(settings.database_url)
    limits = limits_from_env()
    app = FastAPI(title='ft-moulinette', version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return JSONResponse(dict(error=dict(code=exc.code, message=exc.message)), status_code=exc.status)

    @app.exception_handler(ExecutionError)
    async def execution_error(request, exc):
        status = 422 if exc.category == 'user' else 503
        return JSONResponse(dict(error=dict(code=exc.code, message=exc.message)), status_code=status)

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def db():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def client_ip(request):
        if settings.trust_proxy and request.headers.get('x-forwarded-for'):
            return request.headers['x-forwarded-for'].split(',')[-1].strip()
        return request.client.host if request.client else 'inconnu'

    def authenticate(request: Request, session=Depends(db)):
        """Jeton personnel (Bearer, CLI et éditeurs) ou cookie de session (navigateur)."""
        header = request.headers.get('authorization', '')
        if header.startswith('Bearer '):
            row = session.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash(header[7:].strip()),
                                                        ApiToken.revoked.is_(False)))
            user = session.get(User, row.user_id) if row else None
            if user is None or user.disabled:
                raise ApiError(401, 'unauthenticated', 'Jeton invalide ou révoqué.')
            if row.last_used_at is None or now() - row.last_used_at > timedelta(minutes=5):
                row.last_used_at = now()
            request.state.via_cookie = False
            return user
        cookie = request.cookies.get(COOKIE)
        row = session.scalar(select(Session).where(Session.token_hash == token_hash(cookie))) if cookie else None
        user = session.get(User, row.user_id) if row and row.expires_at > now() else None
        if user is None or user.disabled:
            raise ApiError(401, 'unauthenticated', 'Connexion requise.')
        if request.method not in ('GET', 'HEAD'):
            # Cookie ambiant : en-tête personnalisé (impossible à poser depuis un autre site sans CORS) et Origin.
            origin = request.headers.get('origin')
            if request.headers.get(CSRF_HEADER) != '1' or (origin and settings.public_origin
                                                           and origin != settings.public_origin):
                raise ApiError(403, 'csrf', 'Requête d’une autre origine refusée.')
        request.state.via_cookie = True
        return user

    def admin(user=Depends(authenticate)):
        if not user.is_admin:
            raise ApiError(403, 'forbidden', 'Réservé aux administrateurs.')
        return user

    async def json_body(request, limit=16 * 1024):
        raw = await request.body()
        if len(raw) > limit:
            raise ApiError(413, 'too_large', 'Requête trop grande.')
        try:
            data = json.loads(raw or b'{}')
        except ValueError:
            raise ApiError(400, 'invalid_json', 'JSON invalide.') from None
        if not isinstance(data, dict):
            raise ApiError(400, 'invalid_json', 'Objet JSON attendu.')
        return data

    # --- état ---------------------------------------------------------------------------
    @app.get('/api/health')
    def health(session=Depends(db)):
        session.execute(select(1))
        runtime.redis.ping()
        return dict(status='ok', version=__version__)

    @app.get('/api/status')
    def status(user=Depends(authenticate)):
        switch = runtime.switch_state()
        return dict(executions_enabled=switch['enabled'], projects=list(PROJECTS),
                    message=None if switch['enabled'] else 'Exécutions suspendues pour maintenance.',
                    limits=dict(max_upload_bytes=limits.max_upload_bytes, max_files=limits.max_files,
                                max_file_bytes=limits.max_file_bytes, submission_timeout=limits.submission_timeout),
                    quotas=dict(per_user_daily=runtime.quotas.policy.per_user_daily,
                                per_user_concurrent=runtime.quotas.policy.per_user_concurrent))

    # --- authentification ----------------------------------------------------------------
    @app.post('/api/auth/login')
    async def login(request: Request, session=Depends(db)):
        data = await json_body(request)
        name, password = data.get('login'), data.get('password')
        if not isinstance(name, str) or not isinstance(password, str) or len(name) > 64 or len(password) > 256:
            raise ApiError(400, 'invalid_credentials', 'Identifiant et mot de passe requis.')
        keys = ['login:' + name.lower(), 'ip:' + client_ip(request)]
        if not runtime.login_allowed(keys):
            raise ApiError(429, 'too_many_attempts', 'Trop de tentatives : réessaie dans 15 minutes.')
        user = session.scalar(select(User).where(User.login == name))
        valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
        if not valid or user is None or user.disabled:
            runtime.login_failed(keys)
            raise ApiError(401, 'invalid_credentials', 'Identifiant ou mot de passe incorrect.')
        runtime.login_succeeded(keys)
        token, digest = new_token('session')
        session.add(Session(user_id=user.id, token_hash=digest, expires_at=now() + timedelta(hours=settings.session_hours)))
        response = JSONResponse(dict(login=user.login, is_admin=user.is_admin))
        response.set_cookie(COOKIE, token, max_age=settings.session_hours * 3600, httponly=True,
                            secure=settings.cookie_secure, samesite='strict', path='/')
        return response

    @app.post('/api/auth/logout')
    def logout(request: Request, user=Depends(authenticate), session=Depends(db)):
        cookie = request.cookies.get(COOKIE)
        if cookie:
            session.execute(delete(Session).where(Session.token_hash == token_hash(cookie)))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path='/', secure=settings.cookie_secure, httponly=True, samesite='strict')
        return response

    @app.get('/api/me')
    def me(user=Depends(authenticate)):
        return dict(login=user.login, is_admin=user.is_admin)

    @app.post('/api/me/password')
    async def change_password(request: Request, user=Depends(authenticate), session=Depends(db)):
        data = await json_body(request)
        if not verify_password(str(data.get('current', '')), user.password_hash):
            raise ApiError(403, 'invalid_credentials', 'Mot de passe actuel incorrect.')
        try:
            user.password_hash = hash_password(data.get('new'))
        except ValueError as exc:
            raise ApiError(422, 'weak_password', str(exc)) from None
        session.add(user)
        session.execute(delete(Session).where(Session.user_id == user.id))  # déconnecte toutes les sessions
        return Response(status_code=204)

    # --- jetons personnels (CLI, éditeurs) -------------------------------------------------
    @app.get('/api/tokens')
    def tokens(user=Depends(authenticate), session=Depends(db)):
        rows = session.scalars(select(ApiToken).where(ApiToken.user_id == user.id, ApiToken.revoked.is_(False))
                               .order_by(ApiToken.created_at.desc())).all()
        return [dict(id=r.id, name=r.name, prefix=r.prefix, created_at=r.created_at.isoformat(),
                     last_used_at=r.last_used_at.isoformat() if r.last_used_at else None) for r in rows]

    @app.post('/api/tokens')
    async def create_token(request: Request, user=Depends(authenticate), session=Depends(db)):
        data = await json_body(request)
        name = data.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 64:
            raise ApiError(422, 'invalid_name', 'Nom du jeton : 1 à 64 caractères.')
        if session.scalar(select(func.count()).select_from(ApiToken).where(
                ApiToken.user_id == user.id, ApiToken.revoked.is_(False))) >= 10:
            raise ApiError(422, 'too_many_tokens', 'Dix jetons actifs au maximum.')
        token, digest = new_token('pat')
        row = ApiToken(user_id=user.id, name=name.strip(), prefix=token[:12], token_hash=digest)
        session.add(row)
        session.flush()
        return JSONResponse(dict(id=row.id, name=row.name, prefix=row.prefix, token=token), status_code=201)

    @app.delete('/api/tokens/{token_id}')
    def revoke_token(token_id: int, user=Depends(authenticate), session=Depends(db)):
        row = session.get(ApiToken, token_id)
        if row is None or row.user_id != user.id:
            raise ApiError(404, 'not_found', 'Jeton inconnu.')
        row.revoked = True
        return Response(status_code=204)

    # --- soumissions -------------------------------------------------------------------------
    @app.post('/api/submissions')
    async def submit(request: Request, user=Depends(authenticate)):
        length = request.headers.get('content-length')
        if length is None or not length.isdigit():
            raise ApiError(411, 'length_required', 'Content-Length obligatoire.')
        if int(length) > limits.max_upload_bytes * 2 + FORM_MARGIN:
            raise ApiError(413, 'too_large', 'Soumission trop grande.')
        if not runtime.executions_enabled():
            raise ApiError(503, 'maintenance', 'Exécutions suspendues pour maintenance.')
        try:
            form = await request.form(max_files=limits.max_files, max_fields=8, max_part_size=limits.max_upload_bytes)
        except Exception:
            raise ApiError(400, 'invalid_request', 'Formulaire multipart illisible.') from None
        try:
            project, source = form.get('project'), form.get('source')
            if project not in PROJECTS or source not in intake.SOURCES:
                raise ApiError(422, 'invalid_request', 'Projet (libft, printf) et source (archive, files, pasted) requis.')
            options = intake.parse_options(form.get('options'))
            if source == 'archive':
                upload = form.get('archive')
                if upload is None or isinstance(upload, str):
                    raise ApiError(422, 'invalid_request', 'Archive ZIP manquante.')
                data = await upload.read(limits.max_upload_bytes + 1)
                if len(data) > limits.max_upload_bytes:
                    raise ApiError(413, 'too_large', 'Archive trop grande.')
                archive, count = intake.archive_from_zip(data, limits)
            elif source == 'files':
                uploads = [item for item in form.getlist('files') if not isinstance(item, str)]
                try:
                    paths = json.loads(form.get('paths') or '[]')
                except ValueError:
                    raise ApiError(422, 'invalid_request', 'paths : JSON invalide.') from None
                if not isinstance(paths, list):
                    raise ApiError(422, 'invalid_request', 'paths : liste attendue.')
                contents = [await item.read(limits.max_file_bytes + 1) for item in uploads]
                archive, count = intake.archive_from_files(contents, paths, limits)
            else:
                archive, count = intake.archive_from_pasted(form.get('pasted') or '', limits)
            target = intake.check_target(form.get('target') or None, archive, limits)
        finally:
            await form.close()
        submission_id = uuid.uuid4().hex
        user_key = str(user.id)
        try:
            runtime.quotas.reserve(user_key, submission_id)
        except QuotaExceeded as exc:
            raise ApiError(429, exc.code, exc.message) from None
        try:
            with transaction(factory) as session:
                row = Submission(id=submission_id, user_id=user.id, project=project, target=target,
                                 options=options.to_dict(), source=source, status='queued', archive=archive,
                                 archive_sha256=archive_digest(archive), archive_bytes=len(archive), files_count=count)
                session.add(row)
            from .tasks import run_submission
            runtime.queue.enqueue_call(run_submission, args=(submission_id,), job_id=submission_id, unique=True,
                                       timeout=limits.request_timeout + 120, result_ttl=86400, failure_ttl=7 * 86400,
                                       retry=None, description=f'ft-moulinette {project}')
        except Exception:
            runtime.quotas.release(user_key, submission_id)
            with transaction(factory) as session:
                session.execute(delete(Submission).where(Submission.id == submission_id))
            raise
        return JSONResponse(summary_of(row), status_code=202)

    def owned(session, submission_id, user):
        row = session.get(Submission, submission_id) if len(submission_id) == 32 else None
        if row is None or (row.user_id != user.id and not user.is_admin):
            raise ApiError(404, 'not_found', 'Soumission inconnue.')
        return row

    @app.get('/api/submissions')
    def history(limit: int = 50, user=Depends(authenticate), session=Depends(db)):
        rows = session.scalars(select(Submission).where(Submission.user_id == user.id)
                               .order_by(Submission.created_at.desc()).limit(max(1, min(limit, 200)))).all()
        return [summary_of(row) for row in rows]

    @app.get('/api/submissions/{submission_id}')
    def detail(submission_id: str, user=Depends(authenticate), session=Depends(db)):
        row = owned(session, submission_id, user)
        data = summary_of(row)
        data.update(options=row.options, report=row.report, metadata=row.result_metadata, backend=row.backend)
        if row.status == 'queued':
            job_ids = runtime.queue.get_job_ids()
            data['queue_position'] = job_ids.index(row.id) + 1 if row.id in job_ids else None
        return data

    @app.delete('/api/submissions/{submission_id}')
    def remove(submission_id: str, user=Depends(authenticate), session=Depends(db)):
        row = owned(session, submission_id, user)
        if row.status not in FINISHED:
            raise ApiError(409, 'in_progress', 'Soumission en cours : impossible de la supprimer maintenant.')
        session.delete(row)
        return Response(status_code=204)

    # --- administration ---------------------------------------------------------------------
    @app.get('/api/admin/overview')
    def overview(user=Depends(admin), session=Depends(db)):
        since = now() - timedelta(days=7)
        rows = session.execute(select(Submission.status, Submission.outcome, Submission.duration_seconds,
                                      Submission.created_at).where(Submission.created_at >= since)).all()
        today = now().replace(hour=0, minute=0, second=0, microsecond=0)
        outcomes = Counter(r.outcome or r.status for r in rows)
        finished = [r for r in rows if r.status in FINISHED]
        durations = [r.duration_seconds for r in finished if r.duration_seconds]
        per_day = Counter(r.created_at.date().isoformat() for r in rows)
        total_seconds = sum(durations)
        return dict(
            executions=runtime.switch_state(), runner=runtime.runner_health(),
            queue=dict(waiting=len(runtime.queue), **runtime.quotas.usage()),
            submissions=dict(today=sum(1 for r in rows if r.created_at >= today), last_7_days=len(rows),
                             per_day=dict(sorted(per_day.items())), outcomes=dict(outcomes),
                             average_seconds=round(total_seconds / len(durations), 1) if durations else None,
                             failure_rate=round(sum(1 for r in finished if r.status == 'failed') / len(finished), 3)
                             if finished else None,
                             in_progress=sum(1 for r in rows if r.status not in FINISHED)),
            consumption=dict(seconds_7_days=round(total_seconds, 1),
                             estimated_cost_7_days=round(total_seconds * settings.cost_per_second, 4)
                             if settings.cost_per_second else None,
                             note='Estimation applicative, pas une facture Google.'))

    @app.post('/api/admin/executions')
    async def set_executions(request: Request, user=Depends(admin)):
        data = await json_body(request)
        if not isinstance(data.get('enabled'), bool):
            raise ApiError(422, 'invalid_request', '« enabled » : booléen attendu.')
        runtime.set_executions(data['enabled'], user.login)
        return runtime.switch_state()

    @app.post('/api/admin/runner-check')
    def runner_check(user=Depends(admin)):
        from .tasks import check_runner
        job = runtime.queue.enqueue_call(check_runner, job_id=f'runner-check-{int(time.time())}', timeout=120,
                                         result_ttl=3600, at_front=True, description='Vérification du runner')
        return JSONResponse(dict(job=job.id, last=runtime.runner_health()), status_code=202)

    @app.get('/api/admin/users')
    def users(user=Depends(admin), session=Depends(db)):
        rows = session.scalars(select(User).order_by(User.login)).all()
        return [dict(id=r.id, login=r.login, is_admin=r.is_admin, disabled=r.disabled,
                     created_at=r.created_at.isoformat()) for r in rows]

    @app.post('/api/admin/users')
    async def create_user(request: Request, user=Depends(admin), session=Depends(db)):
        data = await json_body(request)
        name = data.get('login')
        if not isinstance(name, str) or not name.isascii() or not 2 <= len(name) <= 64 or not name.replace('-', '').replace('_', '').isalnum():
            raise ApiError(422, 'invalid_login', 'Identifiant : 2 à 64 caractères (lettres, chiffres, - et _).')
        if session.scalar(select(User).where(User.login == name)):
            raise ApiError(409, 'exists', 'Identifiant déjà utilisé.')
        password = generate_password()
        row = User(login=name, password_hash=hash_password(password), is_admin=data.get('is_admin') is True)
        session.add(row)
        session.flush()
        return JSONResponse(dict(id=row.id, login=name, is_admin=row.is_admin, password=password), status_code=201)

    @app.post('/api/admin/users/{user_id}/disable')
    def disable_user(user_id: int, user=Depends(admin), session=Depends(db)):
        row = session.get(User, user_id)
        if row is None:
            raise ApiError(404, 'not_found', 'Utilisateur inconnu.')
        if row.id == user.id:
            raise ApiError(409, 'self', 'Impossible de désactiver son propre compte.')
        row.disabled = True
        session.execute(delete(Session).where(Session.user_id == row.id))
        return Response(status_code=204)

    return app
