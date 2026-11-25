import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
for path in (ROOT / 'runners', ROOT / 'workers' / 'dispatcher'):
    sys.path.insert(0, str(path))

from ft_moulinette_runners.base import ExecutionError, Submission  # noqa: E402
from ft_moulinette_runners.workspace import build_archive  # noqa: E402
from ftm_dispatcher import tasks  # noqa: E402
from ftm_dispatcher.quotas import MemoryQuotas, QuotaExceeded, QuotaPolicy, RedisQuotas  # noqa: E402

REDIS_IMAGE = 'redis:7.4-alpine@sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe'
ARCHIVE = build_archive({'libft.h': b'#include <stddef.h>\n', 'ft_strlen.c': b'int x;\n'})
POLICY = QuotaPolicy(per_user_daily=3, per_user_concurrent=1, global_daily=5, max_in_flight=2,
                     min_interval_seconds=0, reservation_ttl=100)


class QuotaBehaviour:
    """Mêmes attentes pour les deux implémentations."""

    def make(self, policy=POLICY, clock=None):
        raise NotImplementedError

    def refused(self, quotas, user, sid, code):
        with self.assertRaises(QuotaExceeded) as raised:
            quotas.reserve(user, sid)
        self.assertEqual(raised.exception.code, code)

    def test_one_in_flight_per_user_then_release(self):
        quotas = self.make()
        quotas.reserve('alice', 's1')
        self.refused(quotas, 'alice', 's2', 'user_concurrent')
        quotas.release('alice', 's1')
        quotas.reserve('alice', 's2')

    def test_bounded_in_flight_and_daily_caps(self):
        quotas = self.make()
        quotas.reserve('alice', 'a1')
        quotas.reserve('bob', 'b1')
        self.refused(quotas, 'carol', 'c1', 'queue_full')
        for user, sid in (('alice', 'a1'), ('bob', 'b1')):
            quotas.release(user, sid)
        for i in range(2, 4):
            quotas.reserve('alice', f'a{i}')
            quotas.release('alice', f'a{i}')
        self.refused(quotas, 'alice', 'a4', 'user_daily')
        quotas.reserve('bob', 'b2')
        quotas.release('bob', 'b2')
        self.refused(quotas, 'carol', 'c2', 'global_daily')  # 5 soumissions au total aujourd'hui

    def test_minimum_interval(self):
        now = [1000.0]
        quotas = self.make(QuotaPolicy(min_interval_seconds=10), clock=lambda: now[0])
        quotas.reserve('alice', 's1')
        quotas.release('alice', 's1')
        if isinstance(quotas, RedisQuotas):
            return  # le délai Redis s'appuie sur l'horloge du serveur (EX), vérifié ci-dessous
        self.refused(quotas, 'alice', 's2', 'too_soon')
        now[0] += 11
        quotas.reserve('alice', 's2')

    def test_lost_reservations_expire(self):
        now = [1000.0]
        quotas = self.make(clock=lambda: now[0])
        quotas.reserve('alice', 's1')  # worker tué : jamais libérée
        now[0] += 101
        quotas.reserve('alice', 's2')


class MemoryQuotaTests(QuotaBehaviour, unittest.TestCase):
    def make(self, policy=POLICY, clock=None):
        return MemoryQuotas(policy, clock or time.time)


def start_redis():
    if not shutil.which('docker'):
        return None
    started = subprocess.run(['docker', 'run', '-d', '--rm', '-p', '127.0.0.1::6379', REDIS_IMAGE],
                             capture_output=True, text=True)
    if started.returncode:
        return None
    container = started.stdout.strip()
    port = subprocess.run(['docker', 'port', container, '6379/tcp'], capture_output=True, text=True).stdout
    return container, int(port.strip().splitlines()[0].rsplit(':', 1)[1])


class RedisCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        started = start_redis()
        if started is None:
            raise unittest.SkipTest('Redis via Docker indisponible')
        cls.container, port = started
        import redis
        cls.redis = redis.Redis(port=port)
        for _ in range(50):
            try:
                cls.redis.ping()
                break
            except redis.exceptions.ConnectionError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['docker', 'stop', cls.container], capture_output=True)

    def setUp(self):
        self.redis.flushall()


class RedisQuotaTests(QuotaBehaviour, RedisCase):
    def make(self, policy=POLICY, clock=None):
        return RedisQuotas(self.redis, policy, clock=clock or time.time)

    def test_cooldown_uses_redis_expiry(self):
        quotas = self.make(QuotaPolicy(min_interval_seconds=1))
        quotas.reserve('alice', 's1')
        quotas.release('alice', 's1')
        self.refused(quotas, 'alice', 's2', 'too_soon')
        time.sleep(1.2)
        quotas.reserve('alice', 's2')


class DispatchTests(RedisCase):
    def setUp(self):
        super().setUp()
        from rq import Queue
        self.queue = Queue('ftm-submissions', connection=self.redis)
        self.quotas = RedisQuotas(self.redis, POLICY)
        tasks._backend = None
        self.addCleanup(setattr, tasks, '_backend', None)

    def work(self):
        from rq import SimpleWorker
        SimpleWorker([self.queue], connection=self.redis).work(burst=True)

    def test_end_to_end_with_mock_backend(self):
        from ftm_dispatcher.enqueue import enqueue_submission
        submission = Submission('libft', archive=ARCHIVE)
        with mock.patch.dict(os.environ, {'EXECUTION_BACKEND': 'mock'}, clear=False):
            job = enqueue_submission(self.queue, submission, 'alice', self.quotas)
            with mock.patch.object(tasks, '_quotas', lambda: RedisQuotas(self.redis, POLICY)):
                self.work()
        job.refresh()
        result = job.return_value()
        self.assertEqual((result['submission_id'], result['outcome']), (submission.submission_id, 'success'))
        self.assertEqual(self.quotas.usage()['in_flight'], 0)  # réservation libérée par la tâche

    def test_duplicates_never_touch_the_original_reservation(self):
        from ftm_dispatcher.enqueue import SubmissionRefused, enqueue_submission
        submission = Submission('libft', archive=ARCHIVE)
        enqueue_submission(self.queue, submission, 'alice', self.quotas)
        with self.assertRaises(SubmissionRefused) as raised:
            enqueue_submission(self.queue, submission, 'alice', self.quotas)
        self.assertEqual(raised.exception.code, 'duplicate')
        self.assertEqual(self.quotas.usage()['in_flight'], 1)
        self.assertEqual(len(self.queue), 1)

    def test_refusals_before_any_reservation(self):
        from ftm_dispatcher.enqueue import SubmissionRefused, enqueue_submission
        with self.assertRaises(ExecutionError):
            enqueue_submission(self.queue, Submission('libft', archive=b'pas une archive'), 'alice', self.quotas)
        with mock.patch.dict(os.environ, {'FTM_EXECUTIONS_DISABLED': '1'}):
            with self.assertRaises(SubmissionRefused) as raised:
                enqueue_submission(self.queue, Submission('libft', archive=ARCHIVE), 'alice', self.quotas)
        self.assertEqual(raised.exception.code, 'maintenance')
        self.assertEqual((len(self.queue), self.quotas.usage()['in_flight']), (0, 0))


class TaskTests(unittest.TestCase):
    def setUp(self):
        tasks._backend = None
        self.addCleanup(setattr, tasks, '_backend', None)

    def run_task(self, environ):
        quotas = MemoryQuotas(POLICY)
        quotas.reserve('alice', 'a' * 32)
        with mock.patch.dict(os.environ, environ, clear=True):
            result = tasks.execute_submission('a' * 32, 'libft', ARCHIVE, user_key='alice', quotas=quotas)
        self.assertEqual(quotas.usage()['in_flight'], 0)  # libérée dans tous les cas
        return result

    def test_stages_are_reported_in_order(self):
        stages = []
        with mock.patch.dict(os.environ, {'EXECUTION_BACKEND': 'mock'}, clear=True):
            result = tasks.execute_submission('c' * 32, 'libft', ARCHIVE, quotas=MemoryQuotas(POLICY),
                                              on_status=stages.append)
        self.assertEqual(result['outcome'], 'success')
        self.assertEqual(stages, ['preparing', 'running', 'analyzing'])

        def broken(stage):
            raise RuntimeError('base indisponible')
        tasks._backend = None
        with mock.patch.dict(os.environ, {'EXECUTION_BACKEND': 'mock'}, clear=True):
            self.assertEqual(tasks.execute_submission('d' * 32, 'libft', ARCHIVE, quotas=MemoryQuotas(POLICY),
                                                      on_status=broken)['outcome'], 'success')

    def test_misconfiguration_is_an_infrastructure_error(self):
        result = self.run_task({})
        self.assertEqual((result['outcome'], result['error']['code']), ('infrastructure_error', 'configuration'))

    def test_production_never_runs_locally(self):
        result = self.run_task({'EXECUTION_BACKEND': 'local', 'FTM_ENVIRONMENT': 'production'})
        self.assertEqual(result['error']['code'], 'configuration')

    def test_kill_switch_and_user_errors(self):
        self.assertEqual(self.run_task({'EXECUTION_BACKEND': 'mock', 'FTM_EXECUTIONS_DISABLED': '1'})['error']['code'],
                         'disabled')
        quotas = MemoryQuotas(POLICY)
        with mock.patch.dict(os.environ, {'EXECUTION_BACKEND': 'mock'}, clear=True):
            result = tasks.execute_submission('b' * 32, 'minishell', ARCHIVE, quotas=quotas)
        self.assertEqual((result['outcome'], result['error']['category']), ('unsupported', 'user'))


if __name__ == '__main__':
    unittest.main()
