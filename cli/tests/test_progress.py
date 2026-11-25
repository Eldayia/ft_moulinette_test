import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ft_moulinette.engine import run
from test_printf import REFERENCE

ROOT = Path(__file__).resolve().parents[1]
STRLEN = '#include "libft.h"\nsize_t ft_strlen(const char *s){size_t i=0;while(s[i])i++;return i;}\n'


class ProgressTests(unittest.TestCase):
    def project(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name)

    def libft(self):
        root = self.project()
        (root/'libft.h').write_text('#include <stddef.h>\nsize_t ft_strlen(const char *);\n')
        (root/'ft_strlen.c').write_text(STRLEN)
        return root

    def test_libft_progress_reports_every_result_in_order(self):
        seen = []
        rows = run(self.libft(), False, False, 1, 42, 10, False, 'libft', seen.append)
        self.assertTrue(rows)
        self.assertEqual(seen, rows)

    def test_printf_progress_reports_every_result_in_order(self):
        root = self.project()
        (root/'ft_printf.h').write_text('int ft_printf(const char *, ...);\n')
        (root/'printer.c').write_text(REFERENCE)
        seen = []
        rows = run(root/'printer.c', False, False, 1, 42, 10, False, 'printf', seen.append)
        self.assertTrue(any(r['check'].startswith('functional:') for r in rows))
        self.assertEqual(seen, rows)

    def test_cli_progress_lines_on_stderr_and_unchanged_json(self):
        target = str(self.libft()/'ft_strlen.c')
        base = [sys.executable, str(ROOT/'bin'/'ft-moulinette'), target, '--project', 'libft', '--json',
                '--no-norm', '--no-memory', '--no-build', '--iterations', '1']
        plain = subprocess.run(base, capture_output=True, text=True, timeout=120)
        streamed = subprocess.run(base + ['--progress'], capture_output=True, text=True, timeout=120)
        self.assertEqual(plain.returncode, streamed.returncode)
        self.assertEqual(plain.stderr, '')
        self.assertEqual(json.loads(plain.stdout), json.loads(streamed.stdout))
        events = [json.loads(line) for line in streamed.stderr.splitlines()]
        self.assertTrue(all(e['event'] == 'result' for e in events))
        self.assertEqual([e['result'] for e in events], json.loads(streamed.stdout)['results'])


if __name__ == '__main__':
    unittest.main()
