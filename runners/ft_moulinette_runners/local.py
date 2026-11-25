"""LocalRunner : le moteur s'exécute sur la machine courante, sans isolation.

Réservé à l'usage personnel (CLI, éditeurs, interface web locale) et au développement. Il n'est
jamais un moteur acceptable pour des soumissions web d'autres personnes : la configuration le
refuse en production (voir config.py).
"""
import shutil
import sys
import tempfile
import threading
from pathlib import Path

from .base import ExecutionBackend, Health, Submission, user_error
from .execution import BoundedProcess, engine_arguments, interpret
from .limits import Limits
from .workspace import extract_archive

REPO_CLI = Path(__file__).resolve().parents[2] / 'cli'


def default_engine_command():
    launcher = REPO_CLI / 'bin' / 'ft-moulinette'
    if launcher.is_file():
        return [sys.executable, str(launcher)]
    found = shutil.which('ft-moulinette')
    if found:
        return [found]
    raise RuntimeError('Moteur ft-moulinette introuvable.')


def engine_version():
    try:
        from ft_moulinette import __version__
        return __version__
    except ImportError:
        if str(REPO_CLI) not in sys.path and (REPO_CLI / 'ft_moulinette').is_dir():
            sys.path.append(str(REPO_CLI))
            from ft_moulinette import __version__
            return __version__
        return None


class LocalRunner(ExecutionBackend):
    name = 'local'
    isolated = False

    def __init__(self, engine=None, limits=None, grace=5.0):
        self.engine = list(engine) if engine else default_engine_command()
        self.limits = limits or Limits()
        self.grace = grace
        self._running = {}
        self._lock = threading.Lock()

    def capabilities(self):
        return dict(backend=self.name, isolated=self.isolated, projects=['libft', 'printf'],
                    analyzers=['compiler', 'make', 'functional', 'malloc-failure', 'norminette', 'valgrind'],
                    sources=['archive', 'local_path'], function_selection=False, cancel=True,
                    limits=self.limits.to_dict(), engine_version=engine_version())

    def check(self):
        launcher = Path(self.engine[-1])
        if not launcher.is_file():
            return Health(False, f'Moteur introuvable : {launcher}')
        return Health(True, 'Moteur local disponible (sans isolation).')

    def execute(self, submission: Submission, on_event=None):
        limits = submission.limits or self.limits
        with tempfile.TemporaryDirectory(prefix='ftm-local-') as temp:
            if submission.archive is not None:
                root = Path(temp) / 'submission'
                root.mkdir()
                extract_archive(submission.archive, root, limits)
                report_root = str(root)
            else:
                root = submission.local_path.resolve()
                if not root.is_dir():
                    raise user_error('invalid_path', f'Dossier introuvable : {root}')
                report_root = None  # chemins d'origine conservés pour les éditeurs
            target = root
            if submission.target:
                target = root / submission.target
                if not target.is_file():
                    raise user_error('invalid_path', f'Fichier ciblé absent de la soumission : {submission.target}')
            command = [*self.engine, *engine_arguments(target, submission.project, submission.options,
                                                       limits.command_timeout)]
            process = BoundedProcess(command, limits.submission_timeout, limits.max_report_bytes,
                                     limits.max_log_bytes, on_event, self.grace)
            with self._lock:
                self._running[submission.submission_id] = process
            try:
                outcome = process.run()
            finally:
                with self._lock:
                    self._running.pop(submission.submission_id, None)
            return interpret(submission, outcome, limits, self.name, report_root, dict(
                engine_version=engine_version(), tests_version=submission.tests_version or engine_version(),
                sandbox_status='none', isolated=False))

    def cancel(self, submission_id):
        with self._lock:
            process = self._running.get(submission_id)
        if process is None:
            return False
        process.stop(cancelled=True)
        return process.process is not None and process.process.poll() is not None
