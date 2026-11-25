import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ft_moulinette.engine import run, detect_project
from ft_moulinette.printf_cases import GROUPS


REFERENCE = r'''
#include "ft_printf.h"
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>
int ft_printf(const char *format, ...)
{
    va_list ap;
    va_start(ap, format);
    int result = vprintf(format, ap);
    va_end(ap);
    return result;
}
'''


class PrintfTests(unittest.TestCase):
    def fixture(self, body=REFERENCE, nested=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root/'ft_printf.h').write_text('int ft_printf(const char *, ...);\n')
        directory = root/'src' if nested else root
        directory.mkdir(exist_ok=True)
        (directory/'printer.c').write_text(body)
        source = 'src/printer' if nested else 'printer'
        (root/'Makefile').write_text(
            'NAME = libftprintf.a\n'
            f'OBJ = {source}.o\n'
            'all: $(NAME)\n'
            '$(NAME): $(OBJ)\n\tar rcs $@ $^\n'
            f'{source}.o: {source}.c ft_printf.h\n'
            '\tcc -Wall -Wextra -Werror -I. -c $< -o $@\n'
            'clean:\n\trm -f $(OBJ)\n'
            'fclean: clean\n\trm -f $(NAME)\n'
            're: fclean all\n.PHONY: all clean fclean re\n')
        (root/'README.md').write_text(
            '*This activity has been created as part of the 42 curriculum by tester.*\n'
            '# Description\nTest fixture.\n# Instructions\nmake\n# Resources\n'
            'libc; AI used for tests.\n# Algorithm\nDelegates to libc (test oracle only).\n')
        return root

    def results(self, root, build=False, memory=False):
        return run(root, norm=False, memory=memory, iterations=30, seed=123,
                   timeout=5, build=build)

    def test_reference_and_makefile_nested_sources(self):
        root = self.fixture(nested=True)
        rows = self.results(root, build=True)
        functions = [r for r in rows if 'functional:' in r['check']]
        self.assertEqual(len(functions), 2*len(GROUPS))
        self.assertTrue(all(r['status'] == 'pass' for r in functions), functions)
        # The libc oracle deliberately uses a forbidden function; it must be detected.
        failures = [r for r in rows if r['status'] in ('fail', 'missing', 'blocked', 'unavailable')]
        self.assertTrue(failures)
        self.assertTrue(all(r['check'] == 'symbols' for r in failures), failures)
        self.assertFalse((root/'src/printer.o').exists())
        self.assertFalse((root/'libftprintf.a').exists())
        self.assertTrue(any(r['check'] == 'rebuild:printer.c' for r in rows))
        self.assertEqual(detect_project(root/'src/printer.c'), 'printf')
        self.assertEqual(detect_project(root, 'libft'), 'libft')

    def test_wrong_return(self):
        rows = self.results(self.fixture(REFERENCE.replace('return result;', 'return result+1;')))
        self.assertTrue(all(r['status'] == 'fail' for r in rows if 'functional:' in r['check']))

    def test_mutations(self):
        mutations = {
            'nul': ('c', 'if (strchr(format, \'c\')) return 0;'),
            'pointer': ('p', 'if (strchr(format, \'p\')) return 0;'),
            'int_min': ('d', 'if (strchr(format, \'d\')) return 0;'),
            'integer': ('i', 'if (strchr(format, \'i\')) return 0;'),
            'unsigned': ('u', 'if (strchr(format, \'u\')) return 0;'),
            'lower': ('x', 'if (strchr(format, \'x\')) return 0;'),
            'upper': ('X', 'if (strchr(format, \'X\')) return 0;'),
            'percent': ('percent', 'if (strstr(format, "%%")) return 0;'),
            'string': ('s', 'if (strchr(format, \'s\')) return 0;'),
        }
        for name, (group, mutation) in mutations.items():
            with self.subTest(name=name):
                body = REFERENCE.replace('    va_list ap;', mutation+'\n    va_list ap;')
                rows = self.results(self.fixture(body))
                row = next(r for r in rows if r['check'] == 'functional:'+group)
                self.assertEqual(row['status'], 'fail', row)
                self.assertIn('Retour attendu', row['message'])

    def test_binary_comparison(self):
        body = REFERENCE.replace('int result = vprintf(format, ap);', r'''
            char output[200000];
            int result = vsnprintf(output, sizeof(output), format, ap);
            fwrite(output, 1, strlen(output), stdout);
        ''')
        rows = self.results(self.fixture(body))
        row = next(r for r in rows if r['check'] == 'functional:c')
        self.assertEqual(row['status'], 'fail')
        self.assertIn('Octets attendus', row['message'])

    def test_empty_archive(self):
        root = self.fixture()
        path = root/'Makefile'
        path.write_text(path.read_text().replace('ar rcs $@ $^', 'ar rcs $@'))
        rows = self.results(root, build=True)
        self.assertTrue(any(r['check'] == 'archive' and r['status'] == 'fail' for r in rows))
        self.assertTrue(any(r['check'] == 'archive:link' and r['status'] == 'blocked' for r in rows))

    def test_crash_isolated(self):
        body = REFERENCE.replace('    va_list ap;', 'if (strchr(format, \'s\')) abort();\n    va_list ap;')
        rows = self.results(self.fixture(body))
        self.assertEqual(next(r['status'] for r in rows if r['check'] == 'functional:s'), 'fail')
        self.assertEqual(next(r['status'] for r in rows if r['check'] == 'functional:X'), 'pass')

    def test_header_and_presence(self):
        root = self.fixture()
        (root/'ft_printf.h').write_text('long ft_printf(const char *, ...);\n')
        rows = self.results(root)
        self.assertTrue(any(r['check'] == 'prototype' and r['status'] == 'fail' for r in rows))
        self.assertFalse(any(r['status'] == 'missing' and 'libft' in r['file'] for r in rows))

    def test_json_cli(self):
        root = self.fixture()
        result = subprocess.run([sys.executable, '-m', 'ft_moulinette', str(root),
                                 '--no-norm', '--no-memory', '--no-build',
                                 '--iterations', '2', '--json'], capture_output=True, text=True)
        data = json.loads(result.stdout)
        self.assertEqual(data['module'], 'printf-1.1')
        self.assertEqual(result.returncode, 1)  # forbidden libc call
        self.assertTrue(any(r['check'] == 'functional:mixed' for r in data['results']))

    def test_unbuffered_writes(self):
        body = REFERENCE.replace('#include <stdio.h>', '#include <stdio.h>\n#include <unistd.h>')
        body = body.replace('int result = vprintf(format, ap);', '''
            char output[200000];
            int result = vsnprintf(output, sizeof(output), format, ap);
            if (write(1, output, (size_t)result) != result) abort();
        ''')
        rows = self.results(self.fixture(body))
        self.assertTrue(all(r['status'] == 'pass' for r in rows if 'functional:' in r['check']), rows)

    def test_timeout_isolated(self):
        body = REFERENCE.replace('    va_list ap;', 'if (strchr(format, \'s\')) {while (1) {}}\n    va_list ap;')
        root = self.fixture(body)
        rows = run(root, norm=False, memory=False, build=False, iterations=2, timeout=1)
        row = next(r for r in rows if r['check'] == 'functional:s')
        self.assertEqual(row['status'], 'fail')
        self.assertIn('Délai dépassé', row['message'])
        self.assertEqual(next(r['status'] for r in rows if r['check'] == 'functional:X'), 'pass')

    def test_empty_header_is_not_a_prototype(self):
        root = self.fixture()
        (root/'ft_printf.h').write_text('')
        rows = self.results(root)
        self.assertTrue(any(r['check'] == 'prototype' and r['status'] == 'fail' for r in rows))

    def test_missing_flags_and_relink(self):
        root = self.fixture()
        makefile = root/'Makefile'
        makefile.write_text(makefile.read_text().replace('-Wextra ', '').replace(
            '.PHONY: all clean fclean re', '.PHONY: all clean fclean re $(NAME)'))
        rows = self.results(root, build=True)
        for check in ('flags', 'relink'):
            self.assertTrue(any(r['check'] == check and r['status'] == 'fail' for r in rows), rows)

    @unittest.skipUnless(shutil.which('valgrind'), 'Valgrind absent')
    def test_memory_reference_and_leak(self):
        rows = self.results(self.fixture(), memory=True)
        memory = [r for r in rows if r['check'].startswith('memory:')]
        self.assertEqual(len(memory), len(GROUPS))
        self.assertTrue(all(r['status'] == 'pass' for r in memory), memory)
        # Leak only in the string group, so other conversions still execute normally.
        body = REFERENCE.replace('    va_list ap;', '''
            if (!strcmp(format, "<%s>")) {
                void *leak = malloc(17);
                if (!leak) abort();
                memset(leak, 1, 17);
            }
            va_list ap;
        ''')
        rows = self.results(self.fixture(body), memory=True)
        row = next(r for r in rows if r['check'] == 'memory:s')
        self.assertEqual(row['status'], 'fail', row)
        self.assertIn('lost', row['message'])


if __name__ == '__main__':
    unittest.main()
