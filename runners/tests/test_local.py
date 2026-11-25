import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ft_moulinette_runners.base import ExecutionError, Options, Submission
from ft_moulinette_runners.limits import Limits
from ft_moulinette_runners.local import LocalRunner
from ft_moulinette_runners.workspace import build_archive

from helpers import HEADER, STRLEN_BROKEN, STRLEN_OK, STRLEN_WRONG, report, row

FAST = Options(norm=False, memory=False, build=False, iterations=1, seed=1)


def libft(source):
    return build_archive({'libft.h': HEADER.encode(), 'ft_strlen.c': source.encode()})


def fake_engine(directory, body):
    script = Path(directory) / 'engine.py'
    script.write_text('import json, sys, time\n' + body)
    return [sys.executable, str(script)]


class RealEngineTests(unittest.TestCase):
    def run_archive(self, source, **kwargs):
        submission = Submission('libft', archive=libft(source), options=FAST, target='ft_strlen.c', **kwargs)
        events = []
        result = LocalRunner().execute(submission, events.append)
        return result, events

    def test_success_with_relative_paths_and_metadata(self):
        result, events = self.run_archive(STRLEN_OK)
        self.assertEqual(result.outcome, 'success', result.report)
        files = {r['file'] for r in result.report['results']}
        self.assertIn('ft_strlen.c', files)
        self.assertFalse([f for f in files if f.startswith('/tmp')])
        self.assertEqual(result.metadata['backend'], 'local')
        self.assertEqual(result.metadata['engine_version'], '0.3.0')
        self.assertFalse(result.metadata['isolated'])
        self.assertIn('functional', result.metadata['analyzers_used'])
        self.assertEqual(len(events), len(result.report['results']))  # avancement transmis

    def test_failures_are_classified(self):
        self.assertEqual(self.run_archive(STRLEN_WRONG)[0].outcome, 'test_failure')
        self.assertEqual(self.run_archive(STRLEN_BROKEN)[0].outcome, 'compilation_error')

    def test_local_path_keeps_original_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'libft.h').write_text(HEADER)
            (Path(temp) / 'ft_strlen.c').write_text(STRLEN_OK)
            result = LocalRunner().execute(Submission('libft', local_path=temp, options=FAST, target='ft_strlen.c'))
        self.assertEqual(result.outcome, 'success')
        self.assertTrue(any(r['file'] == str(Path(temp).resolve() / 'ft_strlen.c') for r in result.report['results']))

    def test_missing_target_is_a_user_error(self):
        with self.assertRaises(ExecutionError) as raised:
            LocalRunner().execute(Submission('libft', archive=libft(STRLEN_OK), options=FAST, target='absent.c'))
        self.assertEqual(raised.exception.category, 'user')


class FakeEngineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = temp.name

    def execute(self, body, limits=None, **kwargs):
        runner = LocalRunner(engine=fake_engine(self.temp, body), limits=limits, grace=1.0)
        submission = Submission('libft', archive=libft(STRLEN_OK), options=FAST, **kwargs)
        return runner, submission

    def test_global_deadline_stops_the_engine(self):
        runner, submission = self.execute('time.sleep(60)\n',
                                          Limits(command_timeout=1, submission_timeout=1, request_timeout=5))
        started = time.monotonic()
        result = runner.execute(submission)
        self.assertEqual(result.outcome, 'timeout')
        self.assertEqual(result.error.category, 'infrastructure')
        self.assertLess(time.monotonic() - started, 10)

    def test_oversized_output_is_cut(self):
        runner, submission = self.execute("sys.stdout.write('x' * 5_000_000)\nsys.stdout.flush()\ntime.sleep(30)\n",
                                          Limits(max_report_bytes=100_000))
        result = runner.execute(submission)
        self.assertEqual(result.outcome, 'resource_limit')

    def test_forged_report_is_never_a_success(self):
        forged = report([row('functional:strlen', 'fail')])
        forged['summary'] = {'pass': 1}
        runner, submission = self.execute(f'print(json.dumps({forged!r}))\nsys.exit(0)\n')
        result = runner.execute(submission)
        self.assertEqual(result.outcome, 'infrastructure_error')
        self.assertEqual(result.error.code, 'invalid_report')

    def test_garbage_and_crashes(self):
        runner, submission = self.execute('print("Segmentation fault")\nsys.exit(0)\n')
        self.assertEqual(runner.execute(submission).error.code, 'invalid_report')
        runner, submission = self.execute('sys.exit(139)\n')
        self.assertEqual(runner.execute(submission).error.code, 'engine_failed')
        runner, submission = self.execute('print("x: error: cible invalide", file=sys.stderr)\nsys.exit(2)\n')
        result = runner.execute(submission)
        self.assertEqual((result.outcome, result.error.category, result.error.message),
                         ('unsupported', 'user', 'cible invalide'))

    def test_cancel_is_confirmed(self):
        runner, submission = self.execute('time.sleep(60)\n')
        results = []
        thread = threading.Thread(target=lambda: results.append(runner.execute(submission)))
        thread.start()
        deadline = time.time() + 5
        while submission.submission_id not in runner._running and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.2)
        self.assertTrue(runner.cancel(submission.submission_id))
        thread.join(10)
        self.assertEqual(results[0].outcome, 'cancelled')
        self.assertFalse(runner.cancel(submission.submission_id))  # plus rien à annuler

    def test_progress_events_with_broken_consumer(self):
        rows = [row('functional:strlen', 'pass', file='x')]
        body = (f"print(json.dumps(dict(event='result', result={rows[0]!r})), file=sys.stderr, flush=True)\n"
                f"print(json.dumps({report(rows)!r}))\n")
        runner, submission = self.execute(body)

        def broken(event):
            raise RuntimeError('consommateur défaillant')
        result = runner.execute(submission, broken)
        self.assertEqual(result.outcome, 'success')
        self.assertEqual(result.metadata['progress_events'], 1)


if __name__ == '__main__':
    unittest.main()
