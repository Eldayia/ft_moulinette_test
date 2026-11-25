"""CloudRunRunner : client du service runner-api privé déployé sur Cloud Run.

Utilisé par le worker du VPS. Il ne compile ni n'exécute rien localement : il valide et empaquette
la soumission, obtient un ID token Google (audience = URL du service), appelle POST /v1/execute
et valide la réponse, considérée comme non fiable. En cas d'indisponibilité, il échoue fermé : le
résultat est une erreur d'infrastructure, jamais un repli vers une exécution locale.
"""
import base64
import json
import logging
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .base import ExecutionBackend, ExecutionResult, Health, infrastructure_error
from .limits import Limits
from .protocol import build_metadata, parse_response
from .workspace import pack_directory, read_archive

log = logging.getLogger('ft_moulinette.runners.cloudrun')
CLOUD_PLATFORM_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
RESPONSE_MARGIN = 64 * 1024


def _jwt_expiry(token):
    """Date d'expiration (exp) lue sans vérification de signature : sert uniquement au cache."""
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload))['exp']
        return float(value)
    except (IndexError, KeyError, TypeError, ValueError):
        return None


class IdTokenProvider:
    """ID token Google pour un service Cloud Run, mis en cache jusqu'à peu avant son expiration.

    mode « key » : identifiants par défaut, en pratique GOOGLE_APPLICATION_CREDENTIALS vers la clé JSON
    du compte de service ft-moulinette-invoker (google.oauth2.id_token.fetch_id_token).
    mode « wif » : Workload Identity Federation ; identifiants externes par défaut (fichier de
    configuration external_account), puis emprunt d'identité du compte invoker pour générer l'ID token.
    Le jeton n'est jamais journalisé ni exposé en dehors de l'en-tête Authorization.
    """

    def __init__(self, audience, mode='key', service_account=None, refresh_margin=300, clock=time.time,
                 fetcher=None):
        if mode not in ('key', 'wif'):
            raise ValueError('mode attendu : key ou wif')
        if mode == 'wif' and not service_account:
            raise ValueError('le mode wif exige le compte de service à emprunter')
        self.audience = audience
        self.mode = mode
        self.service_account = service_account
        self.refresh_margin = refresh_margin
        self.clock = clock
        self._fetcher = fetcher or self._fetch
        self._token = None
        self._expiry = 0.0
        self._lock = threading.Lock()

    def __repr__(self):  # jamais le jeton
        return f'IdTokenProvider(audience={self.audience!r}, mode={self.mode!r})'

    def token(self):
        with self._lock:
            if self._token and self.clock() < self._expiry - self.refresh_margin:
                return self._token
            try:
                token = self._fetcher()
            except Exception as exc:  # erreurs google-auth, réseau, fichier de clé
                raise infrastructure_error('auth_failed', 'Impossible d’obtenir un ID token Google : '
                                           f'{type(exc).__name__}.') from None
            if not isinstance(token, str) or token.count('.') != 2:
                raise infrastructure_error('auth_failed', 'ID token Google invalide.')
            expiry = _jwt_expiry(token)
            self._token = token
            # Sans exp lisible, on garde la durée documentée (environ une heure), prudemment raccourcie.
            self._expiry = expiry if expiry else self.clock() + 1800
            return token

    def invalidate(self):
        with self._lock:
            self._token, self._expiry = None, 0.0

    def _fetch(self):
        try:
            import google.auth
            import google.auth.transport.requests
            import google.oauth2.id_token
            from google.auth import impersonated_credentials
        except ImportError:
            raise RuntimeError('google-auth absent : installer l’extra « cloudrun ».') from None
        request = google.auth.transport.requests.Request()
        if self.mode == 'key':
            return google.oauth2.id_token.fetch_id_token(request, self.audience)
        source, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
        target = impersonated_credentials.Credentials(
            source_credentials=source, target_principal=self.service_account,
            target_scopes=[CLOUD_PLATFORM_SCOPE], lifetime=3600)
        credentials = impersonated_credentials.IDTokenCredentials(
            target, target_audience=self.audience, include_email=True)
        credentials.refresh(request)
        return credentials.token


def _multipart(metadata, archive):
    boundary = 'ftm-' + secrets.token_hex(16)
    lines = [
        f'--{boundary}'.encode(), b'Content-Disposition: form-data; name="metadata"',
        b'Content-Type: application/json', b'', json.dumps(metadata).encode(),
        f'--{boundary}'.encode(), b'Content-Disposition: form-data; name="archive"; filename="submission.zip"',
        b'Content-Type: application/zip', b'', archive, f'--{boundary}--'.encode(), b'',
    ]
    return b'\r\n'.join(lines), f'multipart/form-data; boundary={boundary}'


class _NotSent(Exception):
    """La requête n'a certainement pas atteint le service : une nouvelle tentative est sûre."""


class CloudRunRunner(ExecutionBackend):
    name = 'cloudrun'
    isolated = True

    def __init__(self, url, token_provider, limits=None, max_attempts=3, backoff=(1.0, 4.0),
                 opener=None, sleep=time.sleep):
        if not url.startswith('https://') and not url.startswith('http://127.0.0.1'):
            raise ValueError('CLOUD_RUN_URL doit être une URL https://')
        self.url = url.rstrip('/')
        self.tokens = token_provider
        self.limits = limits or Limits()
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep

    # --- requêtes ---------------------------------------------------------------
    def _request(self, method, path, body=None, content_type=None, timeout=None, max_bytes=RESPONSE_MARGIN):
        """Un appel HTTP authentifié. Retourne (statut, corps). Lève _NotSent si rien n'a été transmis."""
        request = urllib.request.Request(self.url + path, data=body, method=method)
        request.add_header('Authorization', 'Bearer ' + self.tokens.token())
        request.add_header('Accept', 'application/json')
        if content_type:
            request.add_header('Content-Type', content_type)
        try:
            response = self.opener.open(request, timeout=timeout or self.limits.request_timeout)
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.read(max_bytes + 1)
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (ConnectionRefusedError, socket.gaierror)):
                raise _NotSent(type(reason).__name__) from None
            raise
        with response:
            return response.status, response.read(max_bytes + 1)

    def _json(self, body):
        try:
            return json.loads(body)
        except ValueError:
            return None

    # --- interface ExecutionBackend -------------------------------------------
    def capabilities(self):
        try:
            status, body = self._request('GET', '/v1/capabilities', timeout=30)
        except (_NotSent, OSError) as exc:
            raise infrastructure_error('unreachable', f'Runner injoignable : {type(exc).__name__}.') from None
        data = self._json(body)
        if status != 200 or not isinstance(data, dict):
            raise infrastructure_error('capabilities_failed', f'Capacités indisponibles (HTTP {status}).')
        return data

    def check(self):
        try:
            status, body = self._request('GET', '/readyz', timeout=30)
        except Exception as exc:  # injoignable, délai, échec d'authentification : jamais « disponible »
            detail = getattr(exc, 'message', None) or type(exc).__name__
            return Health(False, f'Runner injoignable : {detail}')
        data = self._json(body) or {}
        if status == 200 and data.get('ready') is True:
            return Health(True, 'Runner Cloud Run prêt.')
        return Health(False, f'Runner non prêt (HTTP {status}) : {data.get("detail", "")}'.strip())

    def execute(self, submission, on_event=None):
        """on_event n'est pas pris en charge : le protocole v1 ne transmet pas d'avancement."""
        limits = submission.limits or self.limits
        archive, target = submission.archive, submission.target
        if archive is None:  # dossier local du VPS ou de l'appelant : empaqueté, jamais exécuté ici
            archive, _ = pack_directory(Path(submission.local_path), limits)
        read_archive(archive, limits)  # validation côté appelant (le runner revalide)
        metadata = build_metadata(submission, limits)
        metadata['target'] = target
        body, content_type = _multipart(metadata, archive)
        started = time.monotonic()
        result = self._send(submission, body, content_type, limits)
        log.info('submission=%s backend=cloudrun outcome=%s duration=%.2f error=%s', submission.submission_id,
                 result.outcome, time.monotonic() - started, result.error.code if result.error else '-')
        return result

    def _send(self, submission, body, content_type, limits):
        sid = submission.submission_id

        def failure(outcome, code, message):
            return ExecutionResult(sid, outcome, None, dict(backend=self.name, interruption=code),
                                   infrastructure_error(code, message))

        refreshed = False
        for attempt in range(1, self.max_attempts + 1):
            try:
                status, raw = self._request('POST', '/v1/execute', body, content_type,
                                            max_bytes=limits.max_report_bytes + RESPONSE_MARGIN)
            except _NotSent as exc:
                if attempt < self.max_attempts:
                    self.sleep(self.backoff[min(attempt - 1, len(self.backoff) - 1)])
                    continue
                return failure('infrastructure_error', 'unreachable', f'Runner injoignable ({exc}).')
            except Exception as exc:
                if hasattr(exc, 'category'):  # échec d'authentification
                    return ExecutionResult(sid, 'infrastructure_error', None,
                                           dict(backend=self.name, interruption=exc.code), exc)
                # Délai ou coupure après envoi : la soumission a pu s'exécuter. Pas de nouvel envoi automatique.
                return failure('infrastructure_error', 'unknown_state',
                               f'Connexion interrompue ({type(exc).__name__}) : état de la soumission inconnu, '
                               'pas de nouvelle tentative automatique.')
            if len(raw) > limits.max_report_bytes + RESPONSE_MARGIN:
                return failure('infrastructure_error', 'response_too_large', 'Réponse du runner trop grande.')
            data = self._json(raw)
            if status == 200:
                try:
                    return parse_response(data, sid, submission.project, limits)
                except ValueError as exc:
                    return failure('infrastructure_error', 'invalid_response', f'Réponse invalide : {exc}')
            if status == 401 and not refreshed:
                refreshed = True
                self.tokens.invalidate()
                continue
            if status == 429 and attempt < self.max_attempts:  # aucune instance disponible : non traité
                self.sleep(self.backoff[min(attempt - 1, len(self.backoff) - 1)])
                continue
            code = (data or {}).get('error', {}).get('code') if isinstance((data or {}).get('error'), dict) else None
            if status == 503 and code == 'sandbox_unavailable':
                return failure('sandbox_unavailable', 'sandbox_unavailable', 'Sandbox indisponible sur le runner.')
            messages = {401: ('auth_failed', 'ID token refusé par Cloud Run (HTTP 401).'),
                        403: ('forbidden', 'Accès refusé par IAM (HTTP 403) : vérifier roles/run.invoker.'),
                        429: ('rate_limited', 'Capacité Cloud Run épuisée (HTTP 429) après plusieurs tentatives.'),
                        500: ('runner_error', 'Erreur interne du runner (HTTP 500).'),
                        503: ('unavailable', 'Runner indisponible (HTTP 503) : état de la soumission inconnu.')}
            code, message = messages.get(status, ('http_error', f'Réponse inattendue du runner (HTTP {status}).'))
            return failure('infrastructure_error', code, message)
        return failure('infrastructure_error', 'unreachable', 'Runner injoignable.')

    def cancel(self, submission_id):
        # Interrompre la requête HTTP ne garantit pas l'arrêt côté Cloud Run : on ne prétend pas annuler.
        # Le délai interne du runner borne l'exécution.
        return False
