import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def test_install_update_and_aliases_after_source_removal(self):
        for shell in ('bash', 'zsh'):
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as directory:
                shell_path = shutil.which(shell)
                if not shell_path:
                    continue
                base = Path(directory)
                home = base / "home with ' quote"
                home.mkdir()
                source = base / 'download with spaces'
                source.mkdir()
                for name in ('ft_moulinette', 'bin'):
                    shutil.copytree(ROOT / name, source / name)
                for name in ('install.sh', 'README.md', 'pyproject.toml'):
                    shutil.copy2(ROOT / name, source / name)
                rc_dir = home / 'zsh config' if shell == 'zsh' else home
                rc_dir.mkdir(exist_ok=True)
                rc = rc_dir / ('.zshrc' if shell == 'zsh' else '.bashrc')
                rc.write_text('# Configuration existante\nexport MOULINETTE_TEST=preserved\n')
                env = dict(os.environ, HOME=str(home), SHELL=shell_path,
                           ZDOTDIR=str(rc_dir), PYTHONPATH='')
                for _ in range(2):
                    result = subprocess.run(['sh', str(source / 'install.sh')],
                                            cwd=base, env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                config = rc.read_text()
                self.assertEqual(config.count('# >>> ft-moulinette >>>'), 1)
                self.assertIn('export MOULINETTE_TEST=preserved', config)
                shutil.rmtree(source)
                executable = home / '.local' / 'bin' / 'ft-moulinette'
                result = subprocess.run([str(executable), '--help'], cwd=base,
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('43 fonctions', result.stdout)
                args = [shell_path]
                if shell == 'bash':
                    args += ['-O', 'expand_aliases']
                args += ['-c', 'source "$1"; eval "moulinette --help"; '
                         'eval "ft-moulinette --help"', 'test', str(rc)]
                result = subprocess.run(args, cwd=base, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.count('43 fonctions'), 2)
