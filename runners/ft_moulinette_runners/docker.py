"""DockerRunner : exécution dans un conteneur sandbox-c local, pour le développement.

Isolation renforcée par rapport à LocalRunner (aucun réseau, racine en lecture seule, utilisateur non
root, capacités retirées, processus, mémoire et CPU bornés), mais **insuffisante pour des utilisateurs
publics** : le noyau de l'hôte est partagé. `isolated` vaut donc False et la configuration le refuse en
production.
"""
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from .base import ExecutionBackend, Health, user_error
from .execution import BoundedProcess, engine_arguments, interpret
from .limits import Limits
from .workspace import extract_archive

MOUNT_POINT = '/submission'
DEFAULT_IMAGE = 'ft-moulinette/sandbox-c:dev'


class DockerRunner(ExecutionBackend):
    name = 'docker'
    isolated = False

    def __init__(self, image=DEFAULT_IMAGE, limits=None, docker='docker', memory='1g', cpus='1', pids=256,
                 tmpfs_size='256m', grace=5.0):
        self.image = image
        self.limits = limits or Limits()
        self.docker = docker
        self.memory, self.cpus, self.pids, self.tmpfs_size = memory, cpus, pids, tmpfs_size
        self.grace = grace
        self._running = {}
        self._lock = threading.Lock()

    def capabilities(self):
        return dict(backend=self.name, isolated=False, projects=['libft', 'printf'], image=self.image,
                    analyzers=['compiler', 'make', 'functional', 'malloc-failure', 'norminette', 'valgrind'],
                    sources=['archive'], function_selection=False, cancel=True, network='none',
                    limits=self.limits.to_dict())

    def check(self):
        try:
            completed = subprocess.run([self.docker, 'image', 'inspect', '--format', '{{.Id}}', self.image],
                                       capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Health(False, f'Docker indisponible : {type(exc).__name__}')
        if completed.returncode:
            return Health(False, f'Image {self.image} absente.')
        return Health(True, f'Image {self.image} disponible (isolation de développement).')

    def command(self, name, input_dir, target, submission, limits):
        return [self.docker, 'run', '--rm', '--name', name, '--pull', 'never', '--network', 'none',
                '--read-only', '--tmpfs', f'/tmp:rw,exec,nosuid,nodev,size={self.tmpfs_size}',
                '--user', '10001:10001', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '--pids-limit', str(self.pids), '--memory', self.memory, '--memory-swap', self.memory,
                '--cpus', self.cpus, '--ulimit', 'core=0', '--ulimit', 'fsize=67108864:67108864',
                '--mount', f'type=bind,src={input_dir},dst={MOUNT_POINT},readonly', '--workdir', '/tmp',
                '--env', 'HOME=/tmp', '--env', 'LANG=C.UTF-8', self.image,
                *engine_arguments(target, submission.project, submission.options, limits.command_timeout)]

    def remove(self, name):
        try:
            completed = subprocess.run([self.docker, 'rm', '--force', name], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f'remove_failed:{type(exc).__name__}'
        return 'removed' if completed.returncode == 0 else 'absent_after_run'

    def execute(self, submission, on_event=None):
        if submission.archive is None:
            raise user_error('unsupported_source', 'DockerRunner accepte uniquement une archive.')
        limits = submission.limits or self.limits
        name = f'ftm-{submission.submission_id}'
        with tempfile.TemporaryDirectory(prefix='ftm-docker-') as temp:
            input_dir = Path(temp) / 'input'
            input_dir.mkdir(mode=0o755)
            Path(temp).chmod(0o755)
            extract_archive(submission.archive, input_dir, limits)
            target = MOUNT_POINT
            if submission.target:
                if not (input_dir / submission.target).is_file():
                    raise user_error('invalid_path', f'Fichier ciblé absent de la soumission : {submission.target}')
                target = f'{MOUNT_POINT}/{submission.target}'
            process = BoundedProcess(self.command(name, input_dir, target, submission, limits),
                                     limits.submission_timeout, limits.max_report_bytes, limits.max_log_bytes,
                                     on_event, self.grace)
            with self._lock:
                self._running[submission.submission_id] = process
            try:
                outcome = process.run()
            finally:
                with self._lock:
                    self._running.pop(submission.submission_id, None)
                # Tuer le client `docker run` n'arrête pas le conteneur : suppression forcée systématique.
                status = self.remove(name)
            return interpret(submission, outcome, limits, self.name, MOUNT_POINT, dict(
                image=self.image, sandbox_status=status, isolated=False))

    def cancel(self, submission_id):
        with self._lock:
            process = self._running.get(submission_id)
        if process is None:
            return False
        process.stop(cancelled=True)
        self.remove(f'ftm-{submission_id}')
        return process.process is not None and process.process.poll() is not None


def docker_available(docker='docker'):
    return shutil.which(docker) is not None
