"""Une source en lecture seule (montage readonly d'une sandbox, dépôt protégé) doit être testée normalement."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from ft_moulinette.engine import run
from test_printf import REFERENCE

LIBFT_MAKEFILE = ('NAME=libft.a\nSRC=ft_strlen.c\nOBJ=$(SRC:.c=.o)\nall: $(NAME)\n$(NAME): $(OBJ)\n\tar rcs $@ $^\n'
                  '%.o: %.c libft.h\n\tcc -Wall -Wextra -Werror -c $< -o $@\nclean:\n\trm -f $(OBJ)\n'
                  'fclean: clean\n\trm -f $(NAME)\nre: fclean all\n.PHONY: all clean fclean re\n')
PRINTF_MAKEFILE = ('NAME = libftprintf.a\nOBJ = printer.o\nall: $(NAME)\n$(NAME): $(OBJ)\n\tar rcs $@ $^\n'
                   'printer.o: printer.c ft_printf.h\n\tcc -Wall -Wextra -Werror -I. -c $< -o $@\n'
                   'clean:\n\trm -f $(OBJ)\nfclean: clean\n\trm -f $(NAME)\nre: fclean all\n'
                   '.PHONY: all clean fclean re\n')


class ReadOnlySourceTests(unittest.TestCase):
    def project(self, files):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name) / 'project'
        (root / 'src').mkdir(parents=True)
        for name, text in files.items():
            (root / name).write_text(text)
        (root / 'src' / 'notes.txt').write_text('sous-dossier en lecture seule\n')
        snapshot = {p: p.stat().st_mode for p in [root, *root.rglob('*')]}
        for path in sorted(snapshot, key=lambda p: len(p.parts), reverse=True):
            path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)

        def cleanup():
            for path in [root, *root.rglob('*')]:
                path.chmod(stat.S_IMODE(path.stat().st_mode) | 0o200)
            temp.cleanup()
        self.addCleanup(cleanup)
        return root, {p: stat.S_IMODE(p.stat().st_mode) for p in snapshot}

    def assert_untouched(self, root, before):
        self.assertEqual({p: stat.S_IMODE(p.stat().st_mode) for p in [root, *root.rglob('*')]}, before)
        self.assertFalse(list(root.rglob('*.o')))

    @unittest.skipIf(os.geteuid() == 0, 'root ignore les permissions en écriture')
    def test_libft_makefile_runs_on_read_only_source(self):
        root, before = self.project({
            'libft.h': '#include <stddef.h>\nsize_t ft_strlen(const char *);\n',
            'ft_strlen.c': '#include "libft.h"\nsize_t ft_strlen(const char *s){size_t i=0;while(s[i])i++;return i;}\n',
            'Makefile': LIBFT_MAKEFILE,
        })
        rows = run(root, False, False, 1, 42, 10, True, 'libft')
        by_check = {r['check']: r for r in rows if r['file'].endswith(('Makefile', 'ft_strlen.c'))}
        self.assertEqual(by_check['make:all']['status'], 'pass', by_check['make:all'])
        self.assertEqual(by_check['archive']['status'], 'pass')
        self.assertFalse([r for r in rows if r['status'] == 'blocked'], [r for r in rows if r['status'] == 'blocked'])
        self.assert_untouched(root, before)

    @unittest.skipIf(os.geteuid() == 0, 'root ignore les permissions en écriture')
    def test_printf_makefile_runs_on_read_only_source(self):
        root, before = self.project({
            'ft_printf.h': 'int ft_printf(const char *, ...);\n', 'printer.c': REFERENCE, 'Makefile': PRINTF_MAKEFILE,
        })
        rows = run(root, False, False, 1, 42, 10, True, 'printf')
        make_all = next(r for r in rows if r['check'] == 'make:all')
        self.assertEqual(make_all['status'], 'pass', make_all)
        self.assertTrue(any(r['check'].startswith('archive:functional') and r['status'] == 'pass' for r in rows))
        self.assertFalse([r for r in rows if r['status'] == 'blocked'])
        self.assert_untouched(root, before)


if __name__ == '__main__':
    unittest.main()
