import http.client
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ft_moulinette_web.__main__ import engine_command
from ft_moulinette_web.jobs import REPO_CLI
from ft_moulinette_web.server import Server


def fake_engine(directory, body):
    """Moteur factice : script Python appelé à la place de la CLI."""
    script = Path(directory) / 'engine.py'
    script.write_text('import json, sys, time\n' + body)
    return [sys.executable, str(script)]


class ServerCase(unittest.TestCase):
    engine = None

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.server = Server(('127.0.0.1', 0), self.engine or engine_command())
        self.server.quiet = True
        self.server.manager.grace = 1.0
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        self.addCleanup(connection.close)
        sent = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            sent.setdefault('Content-Type', 'application/json')
        connection.request(method, path, data, sent)
        response = connection.getresponse()
        raw = response.read()
        payload = json.loads(raw) if response.getheader('Content-Type', '').startswith('application/json') else raw
        return response, payload

    def wait(self, run_id, timeout=120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, job = self.request('GET', f'/api/runs/{run_id}')
            if job['status'] not in ('queued', 'running'):
                return job
            time.sleep(0.1)
        self.fail('exécution non terminée')


class SecurityTests(ServerCase):
    def test_static_page_has_security_headers(self):
        response, body = self.request('GET', '/')
        self.assertEqual(response.status, 200)
        self.assertIn(b'ft-moulinette', body)
        self.assertIn("default-src 'self'", response.getheader('Content-Security-Policy'))
        self.assertEqual(response.getheader('X-Content-Type-Options'), 'nosniff')
        for path in ('/static/app.js', '/static/style.css'):
            self.assertEqual(self.request('GET', path)[0].status, 200)

    def test_static_files_are_whitelisted(self):
        for path in ('/static/../server.py', '/static/jobs.py', '/static/%2e%2e/server.py', '/server.py'):
            self.assertEqual(self.request('GET', path)[0].status, 404, path)

    def test_foreign_host_is_rejected(self):
        response, body = self.request('GET', '/api/runs', headers={'Host': f'attacker.example:{self.port}'})
        self.assertEqual(response.status, 403)
        self.assertIn('Host', body['error'])

    def test_cross_origin_post_is_rejected(self):
        options = dict(target=str(self.temp))
        response, _ = self.request('POST', '/api/runs', options, {'Origin': 'http://attacker.example'})
        self.assertEqual(response.status, 403)
        response, _ = self.request('POST', '/api/runs', options, {'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(response.status, 403)
        self.assertEqual(self.request('GET', '/api/runs')[1]['runs'], [])

    def test_post_requires_json(self):
        response, _ = self.request('POST', '/api/runs', headers={'Content-Type': 'text/plain', 'Content-Length': '2'})
        self.assertEqual(response.status, 415)

    def test_null_body_gets_an_answer(self):
        response, body = self.request('POST', '/api/runs', None, {'Content-Type': 'application/json'})
        self.assertEqual(response.status, 400)
        self.assertIn('objet', body['error'])


class ValidationTests(ServerCase):
    def test_invalid_requests_are_rejected_before_queueing(self):
        (self.temp / 'notes.txt').write_text('x')
        cases = [
            dict(target=''), dict(target='relatif/libft'), dict(target=str(self.temp / 'absent')),
            dict(target=str(self.temp / 'notes.txt')), dict(target=str(self.temp), project='minishell'),
            dict(target=str(self.temp), iterations=0), dict(target=str(self.temp), timeout=True),
            dict(target=str(self.temp), norm='non'), dict(target=str(self.temp), seed=1.5),
        ]
        for options in cases:
            response, body = self.request('POST', '/api/runs', options)
            self.assertEqual(response.status, 400, options)
            self.assertTrue(body['error'])
        self.assertEqual(self.request('GET', '/api/runs')[1]['runs'], [])

    def test_unknown_run(self):
        self.assertEqual(self.request('GET', '/api/runs/000000000000')[0].status, 404)
        self.assertEqual(self.request('DELETE', '/api/runs/000000000000')[0].status, 404)


@unittest.skipUnless((REPO_CLI / 'bin' / 'ft-moulinette').is_file(), 'moteur du dépôt absent')
class RealEngineTests(ServerCase):
    def test_libft_file_run_produces_annotated_report(self):
        (self.temp / 'libft.h').write_text('#include <stddef.h>\nsize_t ft_strlen(const char *s);\n')
        (self.temp / 'ft_strlen.c').write_text(
            '#include "libft.h"\nsize_t ft_strlen(const char *s)\n{\n\tsize_t i = 0;\n\n'
            '\twhile (s[i])\n\t\ti++;\n\treturn (i);\n}\n')
        options = dict(target=str(self.temp / 'ft_strlen.c'), project='libft', norm=False, memory=False,
                       build=False, iterations=1, timeout=10)
        response, job = self.request('POST', '/api/runs', options)
        self.assertEqual(response.status, 202)
        self.assertIn('--no-norm', job['command'])
        job = self.wait(job['id'])
        self.assertEqual(job['status'], 'done', job.get('error'))
        report = job['report']
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(report['module'], 'libft-1.3')
        functional = [r for r in report['results'] if r['check'].startswith('functional')]
        self.assertTrue(functional)
        self.assertTrue(all(r['status'] == 'pass' for r in functional))
        self.assertEqual(functional[0]['relative'], 'ft_strlen.c')
        self.assertTrue(functional[0]['label'].startswith('test fonctionnel'))
        listed = self.request('GET', '/api/runs')[1]['runs']
        self.assertEqual([r['id'] for r in listed], [job['id']])
        self.assertNotIn('report', listed[0])
        self.assertEqual(listed[0]['summary'], report['summary'])

    def test_broken_function_is_reported_as_failure(self):
        (self.temp / 'libft.h').write_text('#include <stddef.h>\nsize_t ft_strlen(const char *s);\n')
        (self.temp / 'ft_strlen.c').write_text(
            '#include "libft.h"\nsize_t ft_strlen(const char *s){size_t i=0;while(s[i])i++;return i+1;}\n')
        options = dict(target=str(self.temp / 'ft_strlen.c'), project='libft', norm=False, memory=False,
                       build=False, iterations=1, timeout=10)
        job = self.wait(self.request('POST', '/api/runs', options)[1]['id'])
        self.assertEqual(job['status'], 'done')
        self.assertTrue(job['report']['summary'].get('fail'))


class SlowEngineTests(ServerCase):
    def setUp(self):
        self.engine = fake_engine(tempfile.mkdtemp(), 'time.sleep(60)\n')
        super().setUp()

    def test_running_and_queued_runs_can_be_cancelled(self):
        first = self.request('POST', '/api/runs', dict(target=str(self.temp)))[1]
        second = self.request('POST', '/api/runs', dict(target=str(self.temp)))[1]
        deadline = time.time() + 5
        while self.request('GET', f'/api/runs/{first["id"]}')[1]['status'] != 'running' and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.request('GET', f'/api/runs/{second["id"]}')[1]['status'], 'queued')
        self.assertEqual(self.request('DELETE', f'/api/runs/{second["id"]}')[1]['status'], 'cancelled')
        started = time.time()
        self.request('DELETE', f'/api/runs/{first["id"]}')
        self.assertEqual(self.wait(first['id'], 10)['status'], 'cancelled')
        self.assertLess(time.time() - started, 5)


class EngineErrorTests(ServerCase):
    def setUp(self):
        self.engine = fake_engine(tempfile.mkdtemp(),
                                  'print("usage: x", file=sys.stderr)\n'
                                  'print("x: error: Indiquer un dossier", file=sys.stderr)\nsys.exit(2)\n')
        super().setUp()

    def test_argparse_error_is_surfaced(self):
        job = self.wait(self.request('POST', '/api/runs', dict(target=str(self.temp)))[1]['id'])
        self.assertEqual(job['status'], 'error')
        self.assertEqual(job['error'], 'Indiquer un dossier')
        self.assertEqual(job['exit_code'], 2)


class EngineFailureExitTests(ServerCase):
    def setUp(self):
        report = dict(schema_version=1, module='libft-1.3', summary=dict(fail=1),
                      results=[dict(file='/elsewhere/x.c', line=3, column=2, check='norm', status='fail', message='m')])
        self.engine = fake_engine(tempfile.mkdtemp(), f'print(json.dumps({report!r}))\nsys.exit(1)\n')
        super().setUp()

    def test_exit_code_one_still_yields_report(self):
        job = self.wait(self.request('POST', '/api/runs', dict(target=str(self.temp)))[1]['id'])
        self.assertEqual(job['status'], 'done')
        self.assertEqual(job['exit_code'], 1)
        row = job['report']['results'][0]
        self.assertEqual(row['relative'], '/elsewhere/x.c')  # hors de la cible : chemin absolu conservé
        self.assertEqual(row['label'], 'norme')


if __name__ == '__main__':
    unittest.main()
