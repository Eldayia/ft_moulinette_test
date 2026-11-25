import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ft_moulinette.report import render


class ReportTests(unittest.TestCase):
    def test_missing_files_are_problems(self):
        with TemporaryDirectory() as directory:
            row = dict(file=str(Path(directory) / 'libft.h'), line=1,
                       status='missing', check='presence', message='Fichier attendu absent')
            output = render([row], directory)
        self.assertIn('1 point à examiner', output)
        self.assertIn('1 manquant', output)
        self.assertIn('libft.h', output)
        self.assertNotIn('Aucun problème', output)

    def test_singular_status_and_external_diagnostic(self):
        with TemporaryDirectory() as directory:
            row = dict(file='/outside/header.h', line=2, status='fail',
                       check='compile', message='Erreur dans un header externe')
            output = render([row], directory, verbose=True)
        self.assertIn('1 en échec', output)
        self.assertIn('/outside/header.h', output)
