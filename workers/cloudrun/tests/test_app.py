"""Service runner-api avec un DOUBLE de la CLI sandbox. Ces tests ne valident pas l'isolation Cloud Run."""
import contextlib
import io
import json
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT / 'runners', ROOT / 'cli', ROOT / 'workers' / 'cloudrun'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from fastapi.testclient import TestClient  # noqa: E402

from ft_moulinette_runners.base import Options, Submission  # noqa: E402
from ft_moulinette_runners.cloudrun import CloudRunRunner  # noqa: E402
from ft_moulinette_runners.limits import Limits  # noqa: E402
from ft_moulinette_runners.protocol import build_metadata, parse_response  # noqa: E402
from ft_moulinette_runners.workspace import build_archive  # noqa: E402
from runner_api.app import create_app  # noqa: E402
from runner_api.settings import GOOGLE_SANDBOX_BIN, Settings, SettingsError  # noqa: E402

HEADER = '#include <stddef.h>\nsize_t ft_strlen(const char *s);\n'
MARKER = 'CODE_SOURCE_CONFIDENTIEL_42'
STRLEN_OK = f'#include "libft.h"\n/* {MARKER} */\nsize_t ft_strlen(const char *s){{size_t i=0;while(s[i])i++;return i;}}\n'
STRLEN_WRONG = '#include "libft.h"\nsize_t ft_strlen(const char *s){size_t i=0;while(s[i])i++;return i+1;}\n'
FAST = Options(norm=False, memory=False, build=False, iterations=1, seed=1)


class RunnerCase(unittest.TestCase):
    mode = 'run'

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        tools = self.temp / 'tools'
        tools.mkdir()
        self.fake = tools / 'sandbox'
        shutil.copy(Path(__file__).with_name('fake_sandbox.py'), self.fake)
        self.fake.chmod(0o755)
        rootfs = self.temp / 'rootfs'
        for inner in ('opt/ft-moulinette/bin/ft-moulinette', 'usr/bin/python3'):
            (rootfs / inner).parent.mkdir(parents=True, exist_ok=True)
            (rootfs / inner).write_text('')
        self.configure(self.mode)
        self.workspace = self.temp / 'workspace'
        self.environ = dict(FTM_ENVIRONMENT='test', FTM_SANDBOX_BIN=str(self.fake), FTM_SANDBOX_ROOTFS=str(rootfs),
                            FTM_WORKSPACE=str(self.workspace), FTM_IMAGE_VERSION='img-test', FTM_TESTS_VERSION='0.3.0')
        self.client = self.make_client()

    def configure(self, mode):
        paths = {'/usr/bin/python3': sys.executable, '/opt/ft-moulinette/bin/ft-moulinette': str(ROOT / 'cli' / 'bin' / 'ft-moulinette')}
        (self.fake.parent / 'fake_config.json').write_text(json.dumps(dict(mode=mode, paths=paths)))

    def make_client(self, **environ):
        env = dict(self.environ, **environ)
        app = create_app(Settings.from_env(env), environ=env)
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def calls(self):
        log = self.fake.parent / 'calls.jsonl'
        return [json.loads(line)['argv'] for line in log.read_text().splitlines()] if log.exists() else []

    def submission(self, source=STRLEN_OK, files=None, **kwargs):
        files = files or {'libft.h': HEADER.encode(), 'ft_strlen.c': source.encode()}
        return Submission('libft', archive=build_archive(files), options=FAST, target='ft_strlen.c', **kwargs)

    def post(self, submission, metadata=None, archive=None, client=None):
        metadata = metadata or build_metadata(submission)
        return (client or self.client).post('/v1/execute', files={
            'metadata': (None, json.dumps(metadata), 'application/json'),
            'archive': ('submission.zip', archive if archive is not None else submission.archive, 'application/zip')})


class ExecuteTests(RunnerCase):
    def test_success_through_the_sandbox_cli(self):
        submission = self.submission()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            response = self.post(submission)
        self.assertEqual(response.status_code, 200, response.text)
        result = parse_response(response.json(), submission.submission_id, 'libft')
        self.assertEqual(result.outcome, 'success')
        self.assertTrue(any(r['file'] == 'ft_strlen.c' for r in result.report['results']))
        self.assertEqual(result.metadata['backend'], 'cloudrun')
        self.assertEqual(result.metadata['image_version'], 'img-test')
        self.assertEqual(result.metadata['sandbox_status'], 'absent_after_run')
        do, delete = self.calls()
        name = f'ftm-{submission.submission_id}'
        self.assertEqual(do[:3], ['do', '--sandbox-name', name])
        self.assertIn('--stdin=false', do)
        self.assertNotIn('--allow-egress', do)
        self.assertNotIn('--write', do)
        mount = do[do.index('--mount') + 1]
        self.assertTrue(mount.startswith('type=bind,src=') and mount.endswith(',dst=/submission,readonly'), mount)
        self.assertEqual(do[do.index('--rootfs') + 1], self.environ['FTM_SANDBOX_ROOTFS'])
        self.assertIn('/submission/ft_strlen.c', do)
        self.assertEqual(delete, ['delete', '--force', name])
        self.assertEqual(list(self.workspace.iterdir()), [])  # espace de soumission supprimé
        logs = output.getvalue()
        self.assertIn('"outcome": "success"', logs)
        self.assertNotIn(MARKER, logs)  # jamais de code source dans les journaux

    def test_failures_and_deduplication(self):
        submission = self.submission(STRLEN_WRONG)
        first = self.post(submission)
        self.assertEqual(first.json()['outcome'], 'test_failure')
        again = self.post(submission)
        self.assertEqual(again.headers.get('x-ftm-deduplicated'), '1')
        self.assertEqual(again.json(), first.json())
        self.assertEqual(sum(call[0] == 'do' for call in self.calls()), 1)

    def test_runner_revalidates_hostile_archives(self):
        import zipfile
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('../../evil.c', 'int x;')
        response = self.post(self.submission(), archive=buffer.getvalue())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['category'], 'user')
        self.assertEqual(self.calls(), [])

    def test_metadata_validation(self):
        submission = self.submission()
        cases = [dict(build_metadata(submission), command='id'), dict(build_metadata(submission), project='minishell')]
        for metadata in cases:
            self.assertEqual(self.post(submission, metadata).status_code, 400)
        response = self.post(submission, dict(build_metadata(submission), functions=['strlen']))
        self.assertEqual((response.status_code, response.json()['outcome']), (200, 'unsupported'))
        self.assertEqual(self.client.post('/v1/execute', content=b'{}', headers={'content-type': 'application/json'}).status_code, 415)
        self.assertEqual(self.calls(), [])

    def test_missing_target_is_rejected(self):
        submission = self.submission()
        metadata = dict(build_metadata(submission), target='absent.c')
        response = self.post(submission, metadata)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.calls(), [])

    def test_oversized_request(self):
        client = self.make_client(FTM_LIMIT_MAX_UPLOAD_BYTES='1000')
        big = build_archive({'a.c': os.urandom(4000).hex().encode()})
        response = self.post(self.submission(), archive=big, client=client)
        self.assertEqual(response.status_code, 413)


class FailClosedTests(RunnerCase):
    def test_missing_sandbox_refuses_execution(self):
        self.fake.unlink()
        self.assertEqual(self.client.get('/readyz').status_code, 503)
        self.assertFalse(self.client.get('/v1/capabilities').json()['ready'])
        response = self.post(self.submission())
        self.assertEqual((response.status_code, response.json()['error']['code']), (503, 'sandbox_unavailable'))

    def test_kill_switch(self):
        client = self.make_client(FTM_EXECUTIONS_DISABLED='1')
        self.assertEqual(client.get('/readyz').status_code, 503)
        self.assertEqual(self.post(self.submission(), client=client).json()['error']['code'], 'disabled')
        self.assertEqual(self.calls(), [])

    def test_production_never_accepts_a_replacement_sandbox_binary(self):
        with self.assertRaises(SettingsError):
            Settings.from_env(dict(self.environ, FTM_ENVIRONMENT='production'))
        settings = Settings.from_env(dict(FTM_ENVIRONMENT='production'))
        self.assertEqual(str(settings.sandbox_bin), GOOGLE_SANDBOX_BIN)

    def test_sandbox_failure_is_an_infrastructure_error(self):
        self.configure('crash')
        submission = self.submission()
        result = parse_response(self.post(submission).json(), submission.submission_id, 'libft')
        self.assertEqual((result.outcome, result.error.category), ('infrastructure_error', 'infrastructure'))
        self.assertEqual(self.calls()[-1][:2], ['delete', '--force'])

    def test_healthz(self):
        self.assertEqual(self.client.get('/healthz').json()['status'], 'ok')
        for path in ('/docs', '/redoc', '/openapi.json'):  # aucune documentation exposée
            self.assertEqual(self.client.get(path).status_code, 404, path)


class TimeoutTests(RunnerCase):
    mode = 'hang'

    def test_deadline_kills_and_deletes_the_sandbox(self):
        client = self.make_client(FTM_LIMIT_COMMAND_TIMEOUT='1', FTM_LIMIT_SUBMISSION_TIMEOUT='2')
        submission = self.submission()
        started = time.monotonic()
        result = parse_response(self.post(submission, client=client).json(), submission.submission_id, 'libft')
        self.assertLess(time.monotonic() - started, 15)
        self.assertEqual(result.outcome, 'timeout')
        self.assertEqual(self.calls()[-1], ['delete', '--force', f'ftm-{submission.submission_id}'])
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_one_execution_at_a_time(self):
        client = self.make_client(FTM_LIMIT_COMMAND_TIMEOUT='3', FTM_LIMIT_SUBMISSION_TIMEOUT='3')
        first = self.submission()
        thread = threading.Thread(target=lambda: self.post(first, client=client))
        thread.start()
        deadline = time.time() + 5
        while not self.calls() and time.time() < deadline:
            time.sleep(0.05)
        second = self.post(self.submission(), client=client)
        self.assertEqual(second.status_code, 429)
        thread.join(20)


class EndToEndTests(RunnerCase):
    """Client CloudRunRunner (VPS) ↔ runner-api réel sur HTTP local, sandbox simulée."""

    def test_client_and_service_agree(self):
        import uvicorn
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        env = dict(self.environ)
        server = uvicorn.Server(uvicorn.Config(create_app(Settings.from_env(env), environ=env), host='127.0.0.1',
                                               port=port, log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(setattr, server, 'should_exit', True)
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.05)

        class Tokens:
            def token(self):
                return 'jeton-de-test'

            def invalidate(self):
                pass
        runner = CloudRunRunner(f'http://127.0.0.1:{port}', Tokens())
        self.assertTrue(runner.check().available)
        self.assertEqual(runner.capabilities()['protocol'], 1)
        with contextlib.redirect_stdout(io.StringIO()):
            ok = runner.execute(self.submission())
            wrong = runner.execute(self.submission(STRLEN_WRONG))
        self.assertEqual((ok.outcome, wrong.outcome), ('success', 'test_failure'))
        self.assertEqual(ok.metadata['backend'], 'cloudrun')


if __name__ == '__main__':
    unittest.main()
