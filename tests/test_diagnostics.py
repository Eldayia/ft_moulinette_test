import unittest
from pathlib import Path
from ft_moulinette.diagnostics import locations

class DiagnosticTests(unittest.TestCase):
    def test_compiler_path_with_spaces(self):
        result=locations('/tmp/copy/ft_strlen.c:7:12: error: bad type','compile','ft_strlen.c',Path('/home/student/my libft'),Path('/tmp/copy'))
        self.assertEqual(result[0]['file'],'/home/student/my libft/ft_strlen.c')
        self.assertEqual((result[0]['line'],result[0]['column']),(7,12))
    def test_norm(self):
        result=locations('Error: TOO_MANY_LINES (line:  42, col:   1): Function too long','norm','ft_strlen.c',Path('/src'),Path('/copy'))
        self.assertEqual(result[0]['line'],42)
    def test_harness_not_reported_as_student(self):
        self.assertEqual(locations('/tmp/test.c:1:1: error: assertion','functional','ft_strlen.c',Path('/src'),Path('/copy')),[])
