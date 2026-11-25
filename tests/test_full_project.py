import tempfile
import unittest
from pathlib import Path
from ft_moulinette.engine import run
from test_harnesses import HEADER, PROTOTYPES
from test_oracles import WRAPPERS

class FullProjectTests(unittest.TestCase):
    def test_complete_reference_project_and_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'libft.h').write_text(HEADER+';\n'.join(PROTOTYPES.values())+';\n')
            includes='#include "libft.h"\n#include <stdlib.h>\n#include <string.h>\n#include <stdio.h>\n#include <ctype.h>\n#include <unistd.h>\n'
            for name,body in WRAPPERS.items(): (root/('ft_'+name+'.c')).write_text(includes+body)
            (root/'Makefile').write_text('NAME=libft.a\nSRC=$(wildcard ft_*.c)\nOBJ=$(SRC:.c=.o)\nall: $(NAME)\n$(NAME): $(OBJ)\n\tar rcs $@ $^\n%.o: %.c libft.h\n\tcc -Wall -Wextra -Werror -c $< -o $@\nclean:\n\trm -f $(OBJ)\nfclean: clean\n\trm -f $(NAME)\nre: fclean all\n.PHONY: all clean fclean re\n')
            rows=run(root,False,False,2,42,15,True)
            for check in ('functional','archive:functional','prototype'):
                matched=[r for r in rows if r['check']==check]
                self.assertEqual(len(matched),43,check)
                self.assertTrue(all(r['status']=='pass' for r in matched),matched)
            for check in ('flags','archiver','relink'):
                self.assertTrue(any(r['check']==check and r['status']=='pass' for r in rows),check)
            rebuilds=[r for r in rows if r['check'].startswith('rebuild:')]
            self.assertEqual(len(rebuilds),44)
            self.assertTrue(all(r['status']=='pass' for r in rebuilds),rebuilds)
            self.assertFalse((root/'libft.a').exists())
