import tempfile
import unittest
from pathlib import Path
from ft_moulinette.audit import audit_build
from ft_moulinette.engine import execute

class BuildAuditTests(unittest.TestCase):
    def test_missing_flags_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            work=Path(temp); project=work/'project'; project.mkdir()
            (project/'x.c').write_text('int example(void){return 0;}')
            (project/'Makefile').write_text('all:\n\tcc -c x.c -o x.o\n\tar rcs libft.a x.o\nfclean:\n\trm -f x.o libft.a\n')
            rows=[]
            audit_build(project,work,execute,lambda *row: rows.append(row),5)
            self.assertTrue(any(r[1]=='flags' and r[2]=='fail' for r in rows))
            self.assertTrue(any(r[1]=='archiver' and r[2]=='pass' for r in rows))
