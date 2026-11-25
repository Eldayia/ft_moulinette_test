import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ft_moulinette_web.__main__ import engine_command, main
from ft_moulinette_web.server import is_loopback


class MainTests(unittest.TestCase):
    def test_remote_listening_requires_explicit_opt_in(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main(['--host', '0.0.0.0', '--port', '0'])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('--allow-remote', stderr.getvalue())

    def test_loopback_detection(self):
        for host in ('127.0.0.1', '::1', '[::1]', 'localhost', '127.0.0.2'):
            self.assertTrue(is_loopback(host), host)
        for host in ('0.0.0.0', '192.168.1.10', 'example.org', '::'):
            self.assertFalse(is_loopback(host), host)

    def test_engine_resolution(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / 'ft-moulinette'
            executable.write_text('#!/bin/sh\n')
            self.assertEqual(engine_command(str(executable)), [str(executable.resolve())])
            with self.assertRaises(ValueError):
                engine_command(str(Path(temp) / 'absent'))
        self.assertTrue(engine_command()[-1].endswith('ft-moulinette'))



class ShutdownTests(unittest.TestCase):
    def serve(self, ignore_sigint=False):
        import signal
        import subprocess
        import sys
        launcher = Path(__file__).resolve().parents[1] / 'bin' / 'ft-moulinette-web'
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        history = Path(temp.name) / 'history.json'
        process = subprocess.Popen(
            [sys.executable, str(launcher), '--port', '0', '--quiet', '--history', str(history)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            preexec_fn=(lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)) if ignore_sigint else None)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        self.assertIn('http://127.0.0.1:', process.stdout.readline())
        for line in process.stdout:
            if line.startswith('Ctrl-C'):
                break
        return process, history

    def test_sigterm_stops_cleanly_and_saves_history(self):
        import signal
        process, history = self.serve()
        process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(15), 0)
        self.assertTrue(history.is_file())  # enregistré à l'arrêt, même vide
        process.stdout.close()
        process.stderr.close()

    def test_sigint_works_even_if_inherited_as_ignored(self):
        import signal
        process, _ = self.serve(ignore_sigint=True)
        process.send_signal(signal.SIGINT)
        self.assertEqual(process.wait(15), 0)
        process.stdout.close()
        process.stderr.close()


if __name__ == '__main__':
    unittest.main()
