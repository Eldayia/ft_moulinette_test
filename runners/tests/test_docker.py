"""DockerRunner avec l'image sandbox-c locale. Isolation de développement, pas celle de Cloud Run.

Les vérifications d'isolation non destructives s'exécutent dès que l'image est présente. Les tests
adversariaux (épuisement de ressources) ne s'exécutent qu'avec FTM_ADVERSARIAL_TESTS=docker, dans un
environnement de validation explicitement autorisé (AGENT.md §21) ; ils restent bornés par le conteneur.
"""
import os
import subprocess
import time
import unittest

from ft_moulinette_runners.base import Options, Submission
from ft_moulinette_runners.docker import DEFAULT_IMAGE, DockerRunner, docker_available
from ft_moulinette_runners.limits import Limits
from ft_moulinette_runners.workspace import build_archive

from helpers import HEADER, STRLEN_OK

IMAGE = os.environ.get('FTM_DOCKER_IMAGE', DEFAULT_IMAGE)
ADVERSARIAL = os.environ.get('FTM_ADVERSARIAL_TESTS') == 'docker'


def image_present():
    if not docker_available():
        return False
    return subprocess.run(['docker', 'image', 'inspect', IMAGE], capture_output=True).returncode == 0


def makefile(recipe):
    """Makefile dont la règle all exécute une sonde, puis échoue pour que sa sortie figure dans le rapport.

    Les recettes sont muettes (@) : seule la sortie des sondes, jamais leur texte, apparaît dans le rapport.
    """
    lines = ''.join(f'\t@{line}\n' for line in recipe)
    return (f'NAME=libft.a\nall:\n{lines}\t@false\nclean:\n\t@true\nfclean: clean\nre: fclean all\n'
            '.PHONY: all clean fclean re\n')


def all_text(report):
    return '\n'.join(r['message'] + '\n' + r.get('raw_message', '') for r in report['results'])


@unittest.skipUnless(image_present(), f'image {IMAGE} absente (docker/cloudrun/Dockerfile.sandbox)')
class DockerRunnerTests(unittest.TestCase):
    def runner(self, limits=None, **kwargs):
        return DockerRunner(IMAGE, limits, grace=2.0, **kwargs)

    def submission(self, files, options=None, **kwargs):
        files = {'libft.h': HEADER, 'ft_strlen.c': STRLEN_OK, **files}
        return Submission('libft', archive=build_archive({k: v.encode() for k, v in files.items()}),
                          options=options or Options(norm=False, memory=False, build=True, iterations=1), **kwargs)

    def assert_container_removed(self, submission):
        listed = subprocess.run(['docker', 'ps', '-a', '-q', '--filter', f'name=ftm-{submission.submission_id}'],
                                capture_output=True, text=True).stdout.strip()
        self.assertEqual(listed, '')

    def test_toolchain_inside_the_image(self):
        submission = self.submission({}, Options(norm=True, memory=True, build=False, iterations=1), target='ft_strlen.c')
        result = self.runner().execute(submission)
        self.assertIn(result.outcome, ('success', 'norm_error'), result.error)
        checks = {r['check']: r['status'] for r in result.report['results']}
        self.assertEqual(checks.get('compile'), 'pass')
        self.assertEqual(checks.get('functional'), 'pass')
        self.assertEqual(checks.get('memory'), 'pass')  # Valgrind fonctionne dans l'image, capacités retirées
        self.assertIn('norminette', result.metadata['analyzers_used'])
        self.assertTrue(all(not r['file'].startswith('/tmp') for r in result.report['results']))
        self.assert_container_removed(submission)

    def test_isolation_probes(self):
        probe = '\n'.join([  # exécuté par python3 ; extension .mk acceptée par la validation des archives
            'import os, socket',
            'for host in (("1.1.1.1", 53), ("169.254.169.254", 80)):',
            '    s = socket.socket(); s.settimeout(2)',
            '    try:',
            '        s.connect(host); print("NET_" + "OPEN", host)',
            '    except OSError:',
            '        print("NET_" + "BLOCKED", host)',
            'print("SECRETS_" + ("VISIBLE" if any(k.startswith(("GOOGLE", "GCP", "K_")) for k in os.environ) else "HIDDEN"))',
        ]) + '\n'
        submission = self.submission({'probe.mk': probe, 'Makefile': makefile([
            'python3 probe.mk',
            '-touch /submission/pwned && echo SUBMISSION_WRITABLE || echo SUBMISSION_READONLY',
            '-touch /opt/ft-moulinette/pwned && echo ENGINE_WRITABLE || echo ENGINE_READONLY',
            'id -u',
        ])})
        result = self.runner().execute(submission)
        text = all_text(result.report)
        self.assertGreaterEqual(text.count('NET_BLOCKED'), 2, text[-2000:])  # make all est lancé plusieurs fois
        self.assertNotIn('NET_OPEN', text)
        self.assertIn('SECRETS_HIDDEN', text)
        self.assertIn('SUBMISSION_READONLY', text)
        self.assertNotIn('SUBMISSION_WRITABLE', text)
        self.assertIn('ENGINE_READONLY', text)
        self.assertNotIn('ENGINE_WRITABLE', text)
        self.assert_container_removed(submission)

    def test_deadline_removes_the_container(self):
        submission = self.submission({'Makefile': makefile(['sleep 300'])})
        limits = Limits(command_timeout=20, submission_timeout=20, request_timeout=30)
        started = time.monotonic()
        result = self.runner(limits).execute(submission)
        self.assertEqual(result.outcome, 'timeout')
        self.assertLess(time.monotonic() - started, 40)
        self.assert_container_removed(submission)


@unittest.skipUnless(ADVERSARIAL and image_present(), 'tests adversariaux : FTM_ADVERSARIAL_TESTS=docker requis')
class AdversarialDockerTests(DockerRunnerTests):
    """Épuisement de ressources, borné par le conteneur (pids, mémoire, tmpfs, délai, sortie)."""

    # Les vérifications de base sont héritées pour leurs outils, pas rejouées.
    test_toolchain_inside_the_image = test_isolation_probes = test_deadline_removes_the_container = None

    def test_fork_bomb_is_bounded(self):
        submission = self.submission({'Makefile': makefile(['-sh -c \'f(){ f|f& }; f\' ; sleep 5', 'echo SURVIVED'])})
        result = self.runner(pids=64).execute(submission)
        self.assertIn(result.outcome, ('test_failure', 'timeout'))
        self.assert_container_removed(submission)

    def test_memory_hog_is_bounded(self):
        submission = self.submission({'Makefile': makefile(['-python3 -c "x = bytearray(3 * 1024**3)"', 'echo AFTER'])})
        result = self.runner(memory='256m').execute(submission)
        self.assertNotIn('infrastructure_error', result.outcome)
        self.assert_container_removed(submission)

    def test_disk_fill_is_bounded(self):
        submission = self.submission({'Makefile': makefile(['-dd if=/dev/zero of=/tmp/fill bs=1M count=1024', 'echo AFTER'])})
        result = self.runner(tmpfs_size='64m').execute(submission)
        self.assertIn('AFTER', all_text(result.report))
        self.assert_container_removed(submission)

    def test_log_flood_is_bounded(self):
        submission = self.submission({'Makefile': makefile(['yes ftm | head -c 50000000'])})
        result = self.runner().execute(submission)
        self.assertLess(len(all_text(result.report)), 2_000_000)  # journaux bornés par le moteur (64 Kio par commande)
        self.assert_container_removed(submission)


if __name__ == '__main__':
    unittest.main()
