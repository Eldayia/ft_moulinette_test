import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ft_moulinette_web.jobs import MAX_HISTORY, JobManager, default_history_path
from test_server import ServerCase, fake_engine

REPORT = dict(schema_version=1, module='libft-1.3', summary=dict(fail=1),
              results=[dict(file='/x/ft_a.c', line=2, column=1, check='norm', status='fail', message='m')])
QUICK = f'print(json.dumps({REPORT!r}))\nsys.exit(1)\n'


class HistoryCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.path = self.temp / 'state' / 'history.json'
        self.engine = fake_engine(self.temp, QUICK)

    def manager(self, engine=None):
        manager = JobManager(engine or self.engine, grace=1.0, progress=False, history=self.path)
        self.addCleanup(manager.close)
        return manager

    def finished(self, manager, job_id, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = manager.get(job_id)
            if job['status'] not in ('queued', 'running'):
                return job
            time.sleep(0.05)
        self.fail('exécution non terminée')

    def entry(self, **changes):
        run = dict(id='0123456789ab', status='done', created=1.0, started=1.0, finished=2.0, exit_code=1,
                   error=None, report=REPORT,
                   options=dict(target='/disparu', project='auto', norm=True, memory=True, build=True,
                                iterations=500, seed=42, timeout=15))
        run.update(changes)
        return run

    def write(self, runs, version=1):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(dict(version=version, runs=runs)))


class PersistenceTests(HistoryCase):
    def test_finished_runs_survive_a_restart(self):
        first = self.manager()
        job = self.finished(first, first.submit(dict(target=str(self.temp)))['id'])
        self.assertEqual(job['status'], 'done')
        first.close()
        self.assertTrue(self.path.is_file())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertFalse(self.path.with_name('history.json.tmp').exists())

        second = self.manager()
        listed = second.list()
        self.assertEqual([r['id'] for r in listed], [job['id']])
        self.assertEqual(listed[0]['summary'], dict(fail=1))
        restored = second.get(job['id'])
        self.assertEqual(restored['report']['results'][0]['check'], 'norm')
        self.assertEqual(restored['command'], job['command'])
        self.assertEqual(restored['exit_code'], 1)

    def test_removed_runs_stay_removed(self):
        first = self.manager()
        job_id = self.finished(first, first.submit(dict(target=str(self.temp)))['id'])['id']
        self.assertTrue(first.remove(job_id))
        self.assertIsNone(first.remove(job_id))
        self.assertEqual(json.loads(self.path.read_text())['runs'], [])
        first.close()
        self.assertEqual(self.manager().list(), [])

    def test_active_run_cannot_be_removed_and_is_not_saved(self):
        slow = self.temp / 'lent'
        slow.mkdir()
        manager = self.manager(fake_engine(slow, 'time.sleep(30)\n'))
        job = manager.submit(dict(target=str(self.temp)))
        self.assertIs(manager.remove(job['id']), False)
        self.assertFalse(self.path.exists())
        manager.cancel(job['id'])
        self.assertEqual(self.finished(manager, job['id'])['status'], 'cancelled')
        saved = json.loads(self.path.read_text())['runs']
        self.assertEqual([(r['id'], r['status']) for r in saved], [(job['id'], 'cancelled')])

    def test_restored_runs_need_not_exist_anymore_but_rerun_is_validated(self):
        self.write([self.entry()])
        manager = self.manager()
        self.assertEqual(manager.get('0123456789ab')['options']['target'], '/disparu')
        with self.assertRaises(ValueError):
            manager.submit(manager.get('0123456789ab')['options'])


class RobustnessTests(HistoryCase):
    def test_invalid_entries_are_skipped(self):
        self.write([
            self.entry(),
            self.entry(id='../../etc'), self.entry(id='aaaaaaaaaaab', status='running'),
            self.entry(id='aaaaaaaaaaac', report=None), self.entry(id='aaaaaaaaaaad', options=dict(target=3)),
            self.entry(id='aaaaaaaaaaae', created='hier'), 'pas un objet',
            self.entry(id='aaaaaaaaaaaf', status='error', report=None, error='boum'),
        ])
        ids = [r['id'] for r in self.manager().list()]
        self.assertEqual(sorted(ids), ['0123456789ab', 'aaaaaaaaaaaf'])

    def test_unknown_version_is_ignored(self):
        self.write([self.entry()], version=99)
        self.assertEqual(self.manager().list(), [])

    def test_history_is_trimmed_to_the_most_recent_runs(self):
        self.write([self.entry(id=f'{i:012x}', created=float(i)) for i in range(MAX_HISTORY + 7)])
        listed = self.manager().list()
        self.assertEqual(len(listed), MAX_HISTORY)
        self.assertEqual(listed[0]['id'], f'{MAX_HISTORY + 6:012x}')  # le plus récent d'abord

    def test_corrupted_file_is_set_aside_not_overwritten(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{ pas du json')
        manager = self.manager()
        self.assertIn('illisible', manager.history_error)
        self.assertEqual(self.path.with_name('history.json.corrompu').read_text(), '{ pas du json')
        job = self.finished(manager, manager.submit(dict(target=str(self.temp)))['id'])
        self.assertEqual([r['id'] for r in json.loads(self.path.read_text())['runs']], [job['id']])
        self.assertIsNone(manager.history_error)

    def test_unwritable_location_is_reported(self):
        blocker = self.temp / 'fichier'
        blocker.write_text('')
        manager = JobManager(self.engine, grace=1.0, progress=False, history=blocker / 'history.json')
        self.addCleanup(manager.close)
        job = self.finished(manager, manager.submit(dict(target=str(self.temp)))['id'])
        self.assertEqual(job['status'], 'done')
        self.assertIn('non enregistré', manager.history_error)

    def test_default_path_follows_xdg_state_home(self):
        with mock.patch.dict(os.environ, {'XDG_STATE_HOME': '/etat'}):
            self.assertEqual(default_history_path(), Path('/etat/ft-moulinette-web/history.json'))
        with mock.patch.dict(os.environ, {'XDG_STATE_HOME': ''}):
            self.assertEqual(default_history_path(), Path.home() / '.local/state/ft-moulinette-web/history.json')


class HistoryApiTests(ServerCase):
    def setUp(self):
        self.engine = fake_engine(tempfile.mkdtemp(), QUICK)
        super().setUp()

    def test_delete_from_history(self):
        job = self.wait(self.request('POST', '/api/runs', dict(target=str(self.temp)))[1]['id'])
        _, listing = self.request('GET', '/api/runs')
        self.assertEqual(listing['history'], dict(enabled=False, error=None))
        response, _ = self.request('DELETE', f'/api/history/{job["id"]}')
        self.assertEqual(response.status, 204)
        self.assertEqual(self.request('GET', '/api/runs')[1]['runs'], [])
        self.assertEqual(self.request('DELETE', f'/api/history/{job["id"]}')[0].status, 404)
        self.assertEqual(self.request('DELETE', '/api/history/pas-un-id')[0].status, 404)

    def test_delete_from_history_requires_same_origin(self):
        job = self.wait(self.request('POST', '/api/runs', dict(target=str(self.temp)))[1]['id'])
        response, _ = self.request('DELETE', f'/api/history/{job["id"]}', headers={'Origin': 'http://attacker.example'})
        self.assertEqual(response.status, 403)
        self.assertEqual(len(self.request('GET', '/api/runs')[1]['runs']), 1)


class ActiveDeleteApiTests(ServerCase):
    def setUp(self):
        self.engine = fake_engine(tempfile.mkdtemp(), 'time.sleep(30)\n')
        super().setUp()

    def test_active_run_returns_conflict(self):
        job = self.request('POST', '/api/runs', dict(target=str(self.temp)))[1]
        response, body = self.request('DELETE', f'/api/history/{job["id"]}')
        self.assertEqual(response.status, 409)
        self.assertIn('Annuler', body['error'])


if __name__ == '__main__':
    unittest.main()
