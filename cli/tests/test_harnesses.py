"""Compile every harness against subject prototypes, without student sources."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from ft_moulinette.cases import CASES, PRELUDE

HEADER = '''#include <stddef.h>
typedef struct s_list {void *content;struct s_list *next;} t_list;
'''
from ft_moulinette.prototypes import PROTOTYPES

class HarnessTests(unittest.TestCase):
    def test_all_harnesses_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'libft.h').write_text(HEADER+';\n'.join(PROTOTYPES.values())+';\n')
            for name,body in CASES.items():
                with self.subTest(function=name):
                    (root/'test.c').write_text(PRELUDE.replace('SEED','42')+'\nint main(void){'+body.replace('ITERATIONS','10')+'\nreturn 0;}')
                    proc=subprocess.run(['cc','-Wall','-Wextra','-Werror','-fsyntax-only',str(root/'test.c')],capture_output=True,text=True)
                    self.assertEqual(proc.returncode,0,proc.stderr)
