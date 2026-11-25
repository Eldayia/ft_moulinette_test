"""CloudRunRunner contre un faux runner-api local. Ces tests ne valident en rien l'isolation Cloud Run."""
import base64
import email.parser
import email.policy
import json
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from ft_moulinette_runners.base import ExecutionError, ExecutionResult, Options, Submission
from ft_moulinette_runners.cloudrun import CloudRunRunner, IdTokenProvider
from ft_moulinette_runners.limits import Limits
from ft_moulinette_runners.protocol import build_response
from ft_moulinette_runners.workspace import build_archive, read_archive

from helpers import HEADER, STRLEN_OK, report, row


def jwt(exp, subject='invoker'):
    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b'=').decode()
    return f'{part({"alg": "RS256"})}.{part({"exp": exp, "sub": subject})}.signature'


class FakeTokens:
    def __init__(self, fail=False):
        self.fail = fail
        self.issued = 0
        self.invalidated = 0

    def token(self):
        if self.fail:
            raise ExecutionError('infrastructure', 'auth_failed', 'Impossible d’obtenir un ID token Google.')
        self.issued += 1
        return f'jeton-{self.issued}'

    def invalidate(self):
        self.invalidated += 1


class FakeRunnerApi:
    """Réponses programmées : liste de (statut, corps, délai)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self):
                length = int(self.headers.get('Content-Length', '0'))
                body = self.rfile.read(length) if length else b''
                outer.requests.append(dict(method=self.command, path=self.path, headers=dict(self.headers), body=body))
                status, payload, delay = outer.responses.pop(0) if outer.responses else (500, b'{}', 0)
                if delay:
                    time.sleep(delay)
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_GET = do_POST = handle_any

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def multipart_parts(request):
    raw = b'Content-Type: ' + request['headers']['Content-Type'].encode() + b'\r\n\r\n' + request['body']
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(raw)
    return {part.get_param('name', header='content-disposition'): part.get_payload(decode=True)
            for part in message.iter_parts()}


class CloudRunCase(unittest.TestCase):
    def setUp(self):
        self.archive = build_archive({'libft.h': HEADER.encode(), 'ft_strlen.c': STRLEN_OK.encode()})
        self.submission = Submission('libft', archive=self.archive, options=Options(memory=False), target='ft_strlen.c')
        self.sleeps = []

    def api(self, *responses):
        api = FakeRunnerApi(responses)
        self.addCleanup(api.close)
        return api

    def runner(self, api, tokens=None, limits=None, url=None):
        return CloudRunRunner(url or api.url, tokens or FakeTokens(), limits, sleep=self.sleeps.append)

    def ok(self, outcome='test_failure', rows=None):
        rows = rows or [row('functional:strlen', 'fail', file='ft_strlen.c')]
        return build_response(ExecutionResult(self.submission.submission_id, outcome, report(rows),
                                              dict(backend='cloudrun', sandbox_status='deleted')))


class ExecuteTests(CloudRunCase):
    def test_request_shape_and_success(self):
        api = self.api((200, self.ok(), 0))
        tokens = FakeTokens()
        result = self.runner(api, tokens).execute(self.submission)
        self.assertEqual(result.outcome, 'test_failure')
        self.assertEqual(result.metadata['sandbox_status'], 'deleted')
        [request] = api.requests
        self.assertEqual((request['method'], request['path']), ('POST', '/v1/execute'))
        self.assertEqual(request['headers']['Authorization'], 'Bearer jeton-1')
        parts = multipart_parts(request)
        metadata = json.loads(parts['metadata'])
        self.assertEqual(metadata['protocol'], 1)
        self.assertEqual(metadata['submission_id'], self.submission.submission_id)
        self.assertEqual(metadata['target'], 'ft_strlen.c')
        self.assertFalse(metadata['options']['memory'])
        self.assertEqual(parts['archive'], self.archive)

    def test_local_directory_is_packed_not_executed(self):
        api = self.api((200, self.ok(), 0))
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'libft.h').write_text(HEADER)
            (Path(temp) / 'ft_strlen.c').write_text(STRLEN_OK)
            (Path(temp) / 'binaire.o').write_bytes(b'\x7fELF')
            submission = Submission('libft', local_path=temp, submission_id=self.submission.submission_id)
            self.runner(api).execute(submission)
        sent = read_archive(multipart_parts(api.requests[0])['archive'])
        self.assertEqual(sorted(sent), ['ft_strlen.c', 'libft.h'])

    def test_invalid_submission_is_never_sent(self):
        api = self.api()
        submission = Submission('libft', archive=b'pas une archive')
        with self.assertRaises(ExecutionError) as raised:
            self.runner(api).execute(submission)
        self.assertEqual(raised.exception.category, 'user')
        self.assertEqual(api.requests, [])

    def test_expired_token_is_refreshed_once(self):
        api = self.api((401, {}, 0), (200, self.ok(), 0))
        tokens = FakeTokens()
        result = self.runner(api, tokens).execute(self.submission)
        self.assertEqual(result.outcome, 'test_failure')
        self.assertEqual(tokens.invalidated, 1)
        self.assertEqual([r['headers']['Authorization'] for r in api.requests], ['Bearer jeton-1', 'Bearer jeton-2'])
        api = self.api((401, {}, 0), (401, {}, 0))
        result = self.runner(api).execute(self.submission)
        self.assertEqual((result.outcome, result.error.code), ('infrastructure_error', 'auth_failed'))

    def test_errors_without_retry(self):
        for status, body, code, outcome in (
            (403, {}, 'forbidden', 'infrastructure_error'),
            (500, {}, 'runner_error', 'infrastructure_error'),
            (503, {}, 'unavailable', 'infrastructure_error'),
            (503, {'error': {'code': 'sandbox_unavailable'}}, 'sandbox_unavailable', 'sandbox_unavailable'),
            (404, {}, 'http_error', 'infrastructure_error'),
        ):
            api = self.api((status, body, 0), (200, self.ok(), 0))
            result = self.runner(api).execute(self.submission)
            self.assertEqual((result.outcome, result.error.code), (outcome, code), status)
            self.assertEqual(result.error.category, 'infrastructure')
            self.assertEqual(len(api.requests), 1, f'{status} ne doit pas être relancé')

    def test_429_is_retried_with_backoff_then_gives_up(self):
        api = self.api((429, {}, 0), (429, {}, 0), (200, self.ok(), 0))
        self.assertEqual(self.runner(api).execute(self.submission).outcome, 'test_failure')
        self.assertEqual(self.sleeps, [1.0, 4.0])
        api = self.api((429, {}, 0), (429, {}, 0), (429, {}, 0), (200, self.ok(), 0))
        result = self.runner(api).execute(self.submission)
        self.assertEqual(result.error.code, 'rate_limited')
        self.assertEqual(len(api.requests), 3)

    def test_timeout_after_sending_is_not_retried(self):
        api = self.api((200, self.ok(), 3), (200, self.ok(), 0))
        limits = Limits(command_timeout=1, submission_timeout=1, request_timeout=2)
        result = self.runner(api, limits=limits).execute(self.submission)
        self.assertEqual((result.outcome, result.error.code), ('infrastructure_error', 'unknown_state'))
        time.sleep(1.5)
        self.assertEqual(len(api.requests), 1)

    def test_connection_refused_is_retried_then_reported(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        result = CloudRunRunner(f'http://127.0.0.1:{port}', FakeTokens(), sleep=self.sleeps.append).execute(self.submission)
        self.assertEqual((result.outcome, result.error.code), ('infrastructure_error', 'unreachable'))
        self.assertEqual(len(self.sleeps), 2)

    def test_forged_or_oversized_responses(self):
        forged = self.ok(outcome='success')  # rapport en échec, résultat annoncé « success »
        api = self.api((200, forged, 0))
        result = self.runner(api).execute(self.submission)
        self.assertEqual(result.error.code, 'invalid_response')
        api = self.api((200, b'x' * 300_000, 0))
        result = self.runner(api, limits=Limits(max_report_bytes=100_000)).execute(self.submission)
        self.assertEqual(result.error.code, 'response_too_large')
        api = self.api((200, b'<html>proxy</html>', 0))
        self.assertEqual(self.runner(api).execute(self.submission).error.code, 'invalid_response')

    def test_authentication_failure_sends_nothing(self):
        api = self.api((200, self.ok(), 0))
        result = self.runner(api, FakeTokens(fail=True)).execute(self.submission)
        self.assertEqual((result.outcome, result.error.code), ('infrastructure_error', 'auth_failed'))
        self.assertEqual(api.requests, [])

    def test_cancel_is_not_claimed(self):
        self.assertFalse(CloudRunRunner('https://runner.example', FakeTokens()).cancel(self.submission.submission_id))


class HealthTests(CloudRunCase):
    def test_ready_not_ready_unreachable(self):
        api = self.api((200, {'ready': True}, 0), (503, {'ready': False, 'detail': 'sandbox absente'}, 0))
        runner = self.runner(api)
        self.assertTrue(runner.check().available)
        health = runner.check()
        self.assertFalse(health.available)
        self.assertIn('sandbox absente', health.detail)
        self.assertEqual(api.requests[0]['path'], '/readyz')
        self.assertFalse(self.runner(api, FakeTokens(fail=True)).check().available)

    def test_url_must_be_https(self):
        with self.assertRaises(ValueError):
            CloudRunRunner('http://runner.example', FakeTokens())


class TokenProviderTests(unittest.TestCase):
    def test_cache_refresh_and_invalidate(self):
        now = [1000.0]
        issued = []

        def fetch():
            issued.append(jwt(now[0] + 3600))
            return issued[-1]
        provider = IdTokenProvider('https://runner.example', clock=lambda: now[0], fetcher=fetch)
        first = provider.token()
        self.assertIs(provider.token(), first)
        now[0] += 3600 - 301  # encore valable plus de 5 minutes
        self.assertIs(provider.token(), first)
        now[0] += 2  # dans la marge de renouvellement
        self.assertIsNot(provider.token(), first)
        provider.invalidate()
        provider.token()
        self.assertEqual(len(issued), 3)
        self.assertNotIn(first, repr(provider))

    def test_failures_never_leak_details(self):
        def fetch():
            raise RuntimeError('clé privée -----BEGIN PRIVATE KEY----- …')
        with self.assertRaises(ExecutionError) as raised:
            IdTokenProvider('https://runner.example', fetcher=fetch).token()
        self.assertEqual(raised.exception.code, 'auth_failed')
        self.assertNotIn('PRIVATE', raised.exception.message)
        with self.assertRaises(ExecutionError):
            IdTokenProvider('https://runner.example', fetcher=lambda: 'pas-un-jwt').token()

    def test_modes_use_the_documented_google_auth_calls(self):
        calls = []
        google = types.ModuleType('google')
        auth = types.ModuleType('google.auth')
        transport = types.ModuleType('google.auth.transport')
        requests_module = types.ModuleType('google.auth.transport.requests')
        oauth2 = types.ModuleType('google.oauth2')
        id_token = types.ModuleType('google.oauth2.id_token')
        impersonated = types.ModuleType('google.auth.impersonated_credentials')
        requests_module.Request = lambda: 'requête'
        id_token.fetch_id_token = lambda request, audience: calls.append(('fetch', request, audience)) or jwt(9e9)
        auth.default = lambda scopes: calls.append(('default', tuple(scopes))) or ('source', 'projet')

        class Impersonated:
            def __init__(self, **kwargs):
                calls.append(('impersonate', kwargs['target_principal'], tuple(kwargs['target_scopes'])))

        class IdCredentials:
            def __init__(self, target, target_audience, include_email):
                calls.append(('id-credentials', target_audience, include_email))
                self.token = None

            def refresh(self, request):
                self.token = jwt(9e9)
        impersonated.Credentials, impersonated.IDTokenCredentials = Impersonated, IdCredentials
        auth.impersonated_credentials, auth.transport = impersonated, transport
        transport.requests, google.auth, google.oauth2, oauth2.id_token = requests_module, auth, oauth2, id_token
        modules = {'google': google, 'google.auth': auth, 'google.auth.transport': transport,
                   'google.auth.transport.requests': requests_module, 'google.oauth2': oauth2,
                   'google.oauth2.id_token': id_token, 'google.auth.impersonated_credentials': impersonated}
        with mock.patch.dict(sys.modules, modules):
            IdTokenProvider('https://runner.example').token()
            IdTokenProvider('https://runner.example', 'wif', 'ft-moulinette-invoker@p.iam.gserviceaccount.com').token()
        scope = ('https://www.googleapis.com/auth/cloud-platform',)
        self.assertEqual(calls, [
            ('fetch', 'requête', 'https://runner.example'),
            ('default', scope),
            ('impersonate', 'ft-moulinette-invoker@p.iam.gserviceaccount.com', scope),
            ('id-credentials', 'https://runner.example', True),
        ])

    def test_wif_requires_a_service_account(self):
        with self.assertRaises(ValueError):
            IdTokenProvider('https://runner.example', 'wif')


if __name__ == '__main__':
    unittest.main()
