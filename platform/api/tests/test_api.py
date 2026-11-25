"""API publique et worker de la plateforme, contre PostgreSQL et Redis réels (conteneurs Docker temporaires).

Le moteur est « mock » : ces tests valident la plateforme, pas l'exécution ni l'isolation du code C.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT / 'platform' / 'api', ROOT / 'runners', ROOT / 'workers' / 'dispatcher'):
    sys.path.insert(0, str(path))

POSTGRES = 'postgres:17-alpine@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73'
REDIS = 'redis:7.4-alpine@sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe'
ORIGIN = 'https://moulinette.test'
FILES = {'libft.h': '#include <stddef.h>\nsize_t ft_strlen(const char *s);\n',
         'ft_strlen.c': '#include "libft.h"\nsize_t ft_strlen(const char *s){size_t i=0;while(s[i])i++;return i;}\n'}


def container(image, port, *args):
    started = subprocess.run(['docker', 'run', '-d', '--rm', '-p', f'127.0.0.1::{port}', *args, image],
                             capture_output=True, text=True)
    if started.returncode:
        return None, None
    cid = started.stdout.strip()
    mapped = subprocess.run(['docker', 'port', cid, f'{port}/tcp'], capture_output=True, text=True).stdout
    return cid, int(mapped.splitlines()[0].rsplit(':', 1)[1])


def zip_of(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


@unittest.skipUnless(shutil.which('docker'), 'Docker requis (PostgreSQL et Redis de test)')
class PlatformCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pg, pg_port = container(POSTGRES, 5432, '-e', 'POSTGRES_PASSWORD=test', '-e', 'POSTGRES_DB=ftm')
        cls.rd, rd_port = container(REDIS, 6379)
        if cls.pg is None or cls.rd is None:
            raise unittest.SkipTest('conteneurs indisponibles')
        for _ in range(120):
            if subprocess.run(['docker', 'exec', cls.pg, 'pg_isready', '-U', 'postgres', '-d', 'ftm', '-h', '127.0.0.1'],
                              capture_output=True).returncode == 0:
                break
            time.sleep(0.25)
        cls.env = {'DATABASE_URL': f'postgresql+psycopg://postgres:test@127.0.0.1:{pg_port}/ftm',
                   'REDIS_URL': f'redis://127.0.0.1:{rd_port}/0', 'FTM_PUBLIC_ORIGIN': ORIGIN,
                   'FTM_ENVIRONMENT': 'test', 'FTM_COOKIE_SECURE': '1', 'EXECUTION_BACKEND': 'mock',
                   'FTM_QUOTA_MIN_INTERVAL': '0', 'FTM_COST_PER_SECOND': '0.0001'}
        cls.patch = mock.patch.dict(os.environ, cls.env)
        cls.patch.start()
        from ftm_platform.manage import migrate
        for attempt in range(20):
            try:
                migrate(cls.env['DATABASE_URL'])
                break
            except Exception:
                if attempt == 19:
                    raise
                time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        from ftm_platform.db import _engines
        for engine in _engines.values():
            engine.dispose()
        _engines.clear()
        cls.patch.stop()
        for cid in (cls.pg, cls.rd):
            if cid:
                subprocess.run(['docker', 'stop', cid], capture_output=True)

    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import text
        from ftm_dispatcher import tasks as dispatcher
        from ftm_platform.app import create_app
        from ftm_platform.db import session_factory, transaction
        from ftm_platform.runtime import Runtime
        from ftm_platform.settings import Settings
        self.factory = session_factory(self.env['DATABASE_URL'])
        with transaction(self.factory) as session:
            session.execute(text('TRUNCATE users, sessions, api_tokens, submissions RESTART IDENTITY CASCADE'))
        self.runtime = Runtime(self.env['REDIS_URL'])
        self.runtime.redis.flushall()
        dispatcher._backend = None
        self.app = create_app(Settings.from_env(), self.runtime)
        self.alice = self.user('alice')
        self.admin_password = self.user('root', admin=True)

    def user(self, login, admin=False):
        from ftm_platform.db import transaction
        from ftm_platform.models import User
        from ftm_platform.security import hash_password
        password = f'mot-de-passe-{login}-42'
        with transaction(self.factory) as session:
            session.add(User(login=login, password_hash=hash_password(password), is_admin=admin))
        return password

    def client(self, login=None, password=None):
        from fastapi.testclient import TestClient
        client = TestClient(self.app, base_url=ORIGIN, headers={'x-ftm-csrf': '1', 'origin': ORIGIN})
        self.addCleanup(client.close)
        if login:
            response = client.post('/api/auth/login', json=dict(login=login, password=password))
            self.assertEqual(response.status_code, 200, response.text)
        return client

    def submit(self, client, source='archive', **extra):
        data = dict(project='libft', source=source, options=json.dumps(dict(memory=False)), **extra.pop('data', {}))
        files = []
        if source == 'archive':
            files = [('archive', ('libft.zip', extra.pop('archive', zip_of(FILES)), 'application/zip'))]
        elif source == 'files':
            files = [('files', (name.rsplit('/', 1)[-1], text.encode(), 'text/plain')) for name, text in FILES.items()]
            data['paths'] = json.dumps(list(FILES))
        else:
            data['pasted'] = json.dumps(extra.pop('pasted', FILES))
        return client.post('/api/submissions', data=data, files=files or None)

    def work(self):
        from rq import SimpleWorker
        SimpleWorker([self.runtime.queue], connection=self.runtime.redis).work(burst=True, logging_level='ERROR')


class AuthTests(PlatformCase):
    def test_login_cookie_and_logout(self):
        client = self.client()
        self.assertEqual(client.get('/api/me').status_code, 401)
        response = client.post('/api/auth/login', json=dict(login='alice', password=self.alice))
        cookie = response.headers['set-cookie'].lower()
        for flag in ('httponly', 'samesite=strict', 'secure', 'path=/'):
            self.assertIn(flag, cookie)
        self.assertEqual(client.get('/api/me').json(), dict(login='alice', is_admin=False))
        self.assertEqual(client.post('/api/auth/logout').status_code, 204)
        self.assertEqual(client.get('/api/me').status_code, 401)

    def test_wrong_password_and_rate_limit(self):
        client = self.client()
        for _ in range(5):
            self.assertEqual(client.post('/api/auth/login', json=dict(login='alice', password='faux-mot-de-passe')).status_code, 401)
        self.assertEqual(client.post('/api/auth/login', json=dict(login='alice', password=self.alice)).status_code, 429)
        self.assertEqual(client.post('/api/auth/login', json=dict(login='inconnu', password='x' * 12)).status_code, 429)

    def test_csrf_protection_for_cookie_sessions(self):
        client = self.client('alice', self.alice)
        no_header = client.post('/api/tokens', json=dict(name='cli'), headers={'x-ftm-csrf': ''})
        self.assertEqual(no_header.status_code, 403)
        foreign = client.post('/api/tokens', json=dict(name='cli'), headers={'origin': 'https://evil.example'})
        self.assertEqual(foreign.status_code, 403)
        self.assertEqual(client.post('/api/tokens', json=dict(name='cli')).status_code, 201)

    def test_personal_tokens_for_cli_and_editors(self):
        client = self.client('alice', self.alice)
        created = client.post('/api/tokens', json=dict(name='vscode')).json()
        token = created['token']
        self.assertTrue(token.startswith('ftm_pat_'))
        self.assertNotIn('token', client.get('/api/tokens').json()[0])  # jamais réaffiché
        from fastapi.testclient import TestClient
        bearer = TestClient(self.app, base_url=ORIGIN, headers={'authorization': f'Bearer {token}'})
        self.addCleanup(bearer.close)
        self.assertEqual(bearer.get('/api/me').json()['login'], 'alice')
        self.assertEqual(self.submit(bearer).status_code, 202)  # pas d'en-tête CSRF : pas de cookie ambiant
        self.assertEqual(client.delete(f'/api/tokens/{created["id"]}').status_code, 204)
        self.assertEqual(bearer.get('/api/me').status_code, 401)

    def test_password_change_closes_sessions(self):
        first = self.client('alice', self.alice)
        second = self.client('alice', self.alice)
        self.assertEqual(first.post('/api/me/password', json=dict(current=self.alice, new='court')).status_code, 422)
        self.assertEqual(first.post('/api/me/password', json=dict(current=self.alice, new='nouveau-mot-de-passe')).status_code, 204)
        self.assertEqual(second.get('/api/me').status_code, 401)


class SubmissionTests(PlatformCase):
    def test_three_sources_run_to_completion(self):
        from ftm_platform.models import Submission
        client = self.client('alice', self.alice)
        ids = []
        for source in ('archive', 'files', 'pasted'):
            response = self.submit(client, source, data=dict(target='ft_strlen.c'))
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()['status'], 'queued')
            ids.append(response.json()['id'])
            self.work()  # une seule soumission en cours par utilisateur : on traite avant la suivante
        for submission_id in ids:
            detail = client.get(f'/api/submissions/{submission_id}').json()
            self.assertEqual((detail['status'], detail['outcome']), ('done', 'success'))
            self.assertEqual(detail['report']['schema_version'], 1)
            self.assertEqual(detail['metadata']['backend'], 'mock')
            with self.factory() as session:
                self.assertIsNone(session.get(Submission, submission_id).archive)  # code non conservé
        self.assertEqual([s['id'] for s in client.get('/api/submissions').json()], ids[::-1])
        self.assertEqual(self.runtime.quotas.usage()['in_flight'], 0)

    def test_hostile_and_invalid_submissions(self):
        client = self.client('alice', self.alice)
        slip = zip_of({'../../etc/evil.c': 'x', **FILES})
        self.assertEqual(self.submit(client, archive=slip).status_code, 422)
        self.assertEqual(self.submit(client, archive=b'pas un zip').status_code, 422)
        self.assertEqual(self.submit(client, 'pasted', pasted={'run.sh': 'rm -rf /'}).status_code, 422)
        self.assertEqual(self.submit(client, data=dict(target='absent.c')).status_code, 422)
        response = client.post('/api/submissions', data=dict(project='minishell', source='archive'))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(client.get('/api/submissions').json(), [])
        self.assertEqual(self.runtime.quotas.usage()['in_flight'], 0)

    def test_quotas_and_ownership(self):
        alice = self.client('alice', self.alice)
        first = self.submit(alice).json()
        second = self.submit(alice)
        self.assertEqual((second.status_code, second.json()['error']['code']), (429, 'user_concurrent'))
        self.user('bob')
        bob = self.client('bob', 'mot-de-passe-bob-42')
        self.assertEqual(bob.get(f'/api/submissions/{first["id"]}').status_code, 404)
        admin = self.client('root', self.admin_password)
        self.assertEqual(admin.get(f'/api/submissions/{first["id"]}').status_code, 200)
        self.assertEqual(alice.delete(f'/api/submissions/{first["id"]}').status_code, 409)  # encore en file
        self.assertEqual(alice.get(f'/api/submissions/{first["id"]}').json()['queue_position'], 1)
        self.work()
        self.assertEqual(alice.delete(f'/api/submissions/{first["id"]}').status_code, 204)

    def test_kill_switch(self):
        alice = self.client('alice', self.alice)
        queued = self.submit(alice).json()
        admin = self.client('root', self.admin_password)
        self.assertEqual(self.client('alice', self.alice).post('/api/admin/executions', json=dict(enabled=False)).status_code, 403)
        self.assertFalse(admin.post('/api/admin/executions', json=dict(enabled=False)).json()['enabled'])
        status = alice.get('/api/status').json()
        self.assertFalse(status['executions_enabled'])
        self.assertIn('maintenance', status['message'])
        self.assertEqual(self.submit(alice).status_code, 503)
        self.work()  # la soumission déjà en file n'est pas exécutée
        detail = alice.get(f'/api/submissions/{queued["id"]}').json()
        self.assertEqual((detail['status'], detail['error']['code']), ('failed', 'disabled'))
        admin.post('/api/admin/executions', json=dict(enabled=True))
        self.assertEqual(self.submit(alice).status_code, 202)

    def test_infrastructure_failures_are_distinguished(self):
        alice = self.client('alice', self.alice)
        submission = self.submit(alice).json()
        with mock.patch.dict(os.environ, {'EXECUTION_BACKEND': ''}):
            from ftm_dispatcher import tasks as dispatcher
            dispatcher._backend = None
            self.work()
        detail = alice.get(f'/api/submissions/{submission["id"]}').json()
        self.assertEqual((detail['status'], detail['outcome'], detail['error']['category']),
                         ('failed', 'infrastructure_error', 'infrastructure'))

    def test_stale_submissions_are_reaped_not_rerun(self):
        from ftm_platform.db import transaction
        from ftm_platform.models import Submission, now
        from ftm_platform.tasks import reap_stale
        alice = self.client('alice', self.alice)
        submission = self.submit(alice).json()
        self.runtime.queue.empty()
        with transaction(self.factory) as session:
            row = session.get(Submission, submission['id'])
            row.status, row.started_at = 'running', now() - timedelta(hours=1)
        self.assertEqual(reap_stale(self.factory, self.runtime), [submission['id']])
        detail = alice.get(f'/api/submissions/{submission["id"]}').json()
        self.assertEqual((detail['status'], detail['error']['code']), ('failed', 'unknown_state'))
        self.assertEqual(self.runtime.quotas.usage()['in_flight'], 0)


class AdminTests(PlatformCase):
    def test_overview_users_and_runner_check(self):
        admin = self.client('root', self.admin_password)
        alice = self.client('alice', self.alice)
        self.submit(alice)
        self.work()
        self.assertEqual(alice.get('/api/admin/overview').status_code, 403)
        overview = admin.get('/api/admin/overview').json()
        self.assertEqual(overview['submissions']['last_7_days'], 1)
        self.assertEqual(overview['submissions']['outcomes'], {'success': 1})
        self.assertIsNotNone(overview['consumption']['estimated_cost_7_days'])
        self.assertTrue(overview['executions']['enabled'])
        self.assertEqual(admin.post('/api/admin/runner-check').status_code, 202)
        self.work()
        runner = admin.get('/api/admin/overview').json()['runner']
        self.assertEqual((runner['backend'], runner['available']), ('mock', True))
        created = admin.post('/api/admin/users', json=dict(login='carol')).json()
        self.assertTrue(created['password'])
        carol = self.client('carol', created['password'])
        self.assertEqual(admin.post(f'/api/admin/users/{created["id"]}/disable').status_code, 204)
        self.assertEqual(carol.get('/api/me').status_code, 401)
        self.assertEqual(admin.post('/api/admin/users', json=dict(login='../x')).status_code, 422)

    def test_migrations_match_models(self):
        from alembic import command
        from ftm_platform.manage import alembic_config
        command.check(alembic_config(self.env['DATABASE_URL']))  # lève si le schéma diverge des modèles


if __name__ == '__main__':
    unittest.main()
