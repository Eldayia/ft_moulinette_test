"""API privée runner-api (Cloud Run). Protégée par IAM : jamais déployée avec accès anonyme.

Endpoints : GET /healthz, GET /readyz, GET /v1/capabilities, POST /v1/execute (protocole v1, multipart).
Une seule exécution à la fois par instance (concurrence Cloud Run de 1, et verrou local en défense).
"""
import json
import os
import threading
import time
from collections import OrderedDict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ft_moulinette_runners.base import ExecutionError, ExecutionResult
from ft_moulinette_runners.config import executions_enabled
from ft_moulinette_runners.protocol import PROTOCOL_VERSION, build_response, parse_metadata
from ft_moulinette_runners.workspace import read_archive

from . import __version__
from .logs import log
from .sandbox import SandboxExecutor
from .settings import Settings

FORM_MARGIN = 64 * 1024  # métadonnées et en-têtes multipart


def error_response(status, category, code, message):
    return JSONResponse(dict(protocol=PROTOCOL_VERSION, error=dict(category=category, code=code, message=message)),
                        status_code=status, headers={'Cache-Control': 'no-store'})


def create_app(settings=None, executor=None, environ=None):
    settings = settings or Settings.from_env(environ)
    executor = executor or SandboxExecutor(settings)
    environ = os.environ if environ is None else environ
    app = FastAPI(title='ft-moulinette runner-api', version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None)
    busy = threading.Lock()
    cache = OrderedDict()   # déduplication par instance : submission_id → réponse déjà produite
    inflight = set()
    state_lock = threading.Lock()

    @app.get('/healthz')
    def healthz():
        return {'status': 'ok', 'version': __version__}

    @app.get('/readyz')
    def readyz():
        ready, detail = executor.readiness()
        if ready and not executions_enabled(environ):
            ready, detail = False, 'Exécutions désactivées par l’administrateur.'
        return JSONResponse(dict(ready=ready, detail=detail), status_code=200 if ready else 503,
                            headers={'Cache-Control': 'no-store'})

    @app.get('/v1/capabilities')
    def capabilities():
        ready, detail = executor.readiness()
        return dict(protocol=PROTOCOL_VERSION, service_version=__version__, backend='cloudrun', isolated=True,
                    ready=ready, projects=['libft', 'printf'], function_selection=False,
                    analyzers=['compiler', 'make', 'functional', 'malloc-failure', 'norminette', 'valgrind'],
                    sanitizers=[], image_version=settings.image_version, tests_version=settings.tests_version,
                    limits=settings.limits.to_dict(), network='blocked', cancel=False)

    @app.post('/v1/execute')
    async def execute(request: Request):
        limits = settings.limits
        if not executions_enabled(environ):
            return error_response(503, 'infrastructure', 'disabled', 'Exécutions désactivées par l’administrateur.')
        length = request.headers.get('content-length')
        if length is None or not length.isdigit():
            return error_response(411, 'user', 'length_required', 'Content-Length obligatoire.')
        if int(length) > limits.max_upload_bytes + FORM_MARGIN:
            return error_response(413, 'user', 'too_large', 'Requête trop grande.')
        content_type = request.headers.get('content-type', '')
        if not content_type.startswith('multipart/form-data'):
            return error_response(415, 'user', 'unsupported_media_type', 'multipart/form-data attendu.')
        try:
            form = await request.form(max_files=1, max_fields=1, max_part_size=FORM_MARGIN)
        except Exception:
            return error_response(400, 'user', 'invalid_request', 'Corps multipart illisible.')
        try:
            if set(form.keys()) != {'metadata', 'archive'}:
                return error_response(400, 'user', 'invalid_request', 'Parties attendues : metadata et archive.')
            metadata, upload = form['metadata'], form['archive']
            if not isinstance(metadata, str) or isinstance(upload, str):
                return error_response(400, 'user', 'invalid_request', 'metadata (texte) et archive (fichier) attendus.')
            archive = await upload.read(limits.max_upload_bytes + 1)
        finally:
            await form.close()
        if len(archive) > limits.max_upload_bytes:
            return error_response(413, 'user', 'too_large', f'Archive supérieure à {limits.max_upload_bytes} octets.')
        try:
            fields, effective = parse_metadata(json.loads(metadata), limits)
        except ValueError:
            return error_response(400, 'user', 'invalid_request', 'Métadonnées JSON illisibles.')
        except ExecutionError as exc:
            if exc.code in ('unsupported', 'unsupported_protocol'):
                result = ExecutionResult(json.loads(metadata).get('submission_id', '0' * 32), 'unsupported',
                                         None, dict(backend='cloudrun'), exc)
                return JSONResponse(build_response(result), headers={'Cache-Control': 'no-store'})
            return error_response(400, exc.category, exc.code, exc.message)
        sid = fields['submission_id']
        try:
            read_archive(archive, effective)  # revalidation complète côté runner, avant toute sandbox
        except ExecutionError as exc:
            return error_response(422, exc.category, exc.code, exc.message)
        with state_lock:
            if sid in cache:
                return JSONResponse(cache[sid], headers={'Cache-Control': 'no-store', 'X-Ftm-Deduplicated': '1'})
            if sid in inflight:
                return error_response(409, 'infrastructure', 'duplicate_in_progress', 'Soumission déjà en cours.')
            if not busy.acquire(blocking=False):
                return error_response(429, 'infrastructure', 'busy', 'Runner occupé.')
            inflight.add(sid)
        started = time.monotonic()
        try:
            ready, detail = executor.readiness()
            if not ready:
                log('ERROR', 'sandbox indisponible', submission_id=sid, detail=detail, error_code='sandbox_unavailable')
                return error_response(503, 'infrastructure', 'sandbox_unavailable', detail)
            try:
                result = await run_in_threadpool(executor.execute, fields, archive, effective)
            except ExecutionError as exc:
                if exc.category == 'user':
                    return error_response(422, 'user', exc.code, exc.message)
                raise
            payload = build_response(result)
            with state_lock:
                cache[sid] = payload
                while len(cache) > settings.max_cached_results:
                    cache.popitem(last=False)
            log('INFO', 'soumission traitée', submission_id=sid, backend='cloudrun', outcome=result.outcome,
                duration_seconds=round(time.monotonic() - started, 3), project=fields['project'],
                tests_version=settings.tests_version, image_version=settings.image_version,
                sandbox_status=result.metadata.get('sandbox_status'),
                error_category=result.error.category if result.error else None,
                error_code=result.error.code if result.error else None)
            return JSONResponse(payload, headers={'Cache-Control': 'no-store'})
        except Exception as exc:  # jamais de trace ni de contenu dans la réponse
            log('ERROR', 'erreur interne', submission_id=sid, detail=type(exc).__name__, error_code='internal')
            return error_response(500, 'infrastructure', 'internal', 'Erreur interne du runner.')
        finally:
            with state_lock:
                inflight.discard(sid)
            busy.release()

    return app


def main():
    import uvicorn
    port = int(os.environ.get('PORT', '8080'))
    uvicorn.run(create_app(), host='0.0.0.0', port=port, log_level='warning', access_log=False)


if __name__ == '__main__':
    main()
