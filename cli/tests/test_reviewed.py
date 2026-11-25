import contextlib
import io
import json
import unittest
from unittest.mock import patch
from ft_moulinette.__main__ import main

class ReviewedTests(unittest.TestCase):
    def invoke(self, *arguments):
        rows = [
            dict(file='/tmp/libft/README.md',line=1,check='review',status='manual',message='README'),
            dict(file='/tmp/libft',line=1,check='review',status='manual',message='Projet'),
            dict(file='/tmp/libft/a.c',line=1,check='compile',status='fail',message='Erreur'),
        ]
        output=io.StringIO()
        with patch('sys.argv',['moulinette','/tmp/libft','--json',*arguments]), patch('ft_moulinette.__main__.run',return_value=rows), contextlib.redirect_stdout(output):
            code=main()
        return code,json.loads(output.getvalue())['summary']

    def test_all_preserves_errors(self):
        code,summary=self.invoke('--reviewed','all')
        self.assertEqual(code,1)
        self.assertEqual(summary,{'reviewed':2,'fail':1})

    def test_selective_and_no_persistence(self):
        self.assertEqual(self.invoke('--reviewed','readme')[1],{'reviewed':1,'manual':1,'fail':1})
        self.assertEqual(self.invoke()[1],{'manual':2,'fail':1})
