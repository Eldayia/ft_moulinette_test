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


if __name__ == '__main__':
    unittest.main()
