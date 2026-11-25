import tempfile
import unittest
from pathlib import Path
from ft_moulinette.engine import run
from ft_moulinette.cases import CASES, FUNCTIONS

class EngineTests(unittest.TestCase):
    def fixture(self, body):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        (root/'libft.h').write_text('#include <stddef.h>\nsize_t ft_strlen(const char *s);\n')
        (root/'ft_strlen.c').write_text('#include "libft.h"\n'+body)
        return root
    def test_coverage(self): self.assertEqual(set(FUNCTIONS),set(CASES))
    def test_correct_partial(self):
        root=self.fixture('size_t ft_strlen(const char *s){size_t n=0;while(s[n])n++;return n;}')
        rows=run(root,False,False,10,42,2,False)
        self.assertTrue(any(r['check']=='functional' and r['status']=='pass' for r in rows))
        self.assertTrue(any(r['status']=='missing' for r in rows))
        self.assertFalse((root/'ft_strlen.o').exists())
        self.assertFalse(any(r['status'] in ('manual', 'reviewed') for r in rows))
    def test_wrong(self):
        root=self.fixture('size_t ft_strlen(const char *s){(void)s;return 0;}')
        rows=run(root/'ft_strlen.c',False,False,10,42,2,False)
        self.assertTrue(any(r['check']=='functional' and r['status']=='fail' for r in rows))
        self.assertFalse(any(r['status']=='missing' for r in rows))
    def test_silent_crash(self):
        root=self.fixture('#include <signal.h>\nsize_t ft_strlen(const char *s){(void)s;raise(SIGSEGV);return 0;}')
        rows=run(root/'ft_strlen.c',False,False,10,42,2,False)
        result=next(r for r in rows if r['check']=='functional')
        self.assertEqual(result['status'], 'fail')
        self.assertIn('SIGSEGV', result['message'])
    def test_timeout(self):
        root=self.fixture('size_t ft_strlen(const char *s){(void)s;while(1){}return 0;}')
        rows=run(root/'ft_strlen.c',False,False,10,42,1,False)
        self.assertTrue(any('Délai dépassé' in r['message'] for r in rows))
    def test_compile_error(self):
        root=self.fixture('bad syntax')
        rows=run(root,False,False,10,42,2,False)
        self.assertTrue(any(r['check']=='compile' and r['status']=='fail' for r in rows))

if __name__=='__main__': unittest.main()
