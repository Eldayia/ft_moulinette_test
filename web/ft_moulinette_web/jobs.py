"""File d'exécutions : chaque exécution lance la CLI avec --json dans un sous-processus."""
import json
import os
import re
import shlex
import signal
import subprocess
import threading
import time
import uuid
from collections import Counter, OrderedDict
from pathlib import Path

import sys

# Dans le dépôt, le moteur est le dossier voisin cli/ ; ajouté en fin de chemin pour ne rien masquer.
REPO_CLI = Path(__file__).resolve().parents[2] / 'cli'
if (REPO_CLI / 'ft_moulinette').is_dir() and str(REPO_CLI) not in sys.path:
    sys.path.append(str(REPO_CLI))

PROJECTS = ('auto', 'libft', 'printf')
ACTIVE = ('queued', 'running')
MAX_QUEUED = 20
MAX_HISTORY = 50
# Statuts qui donnent le code de sortie 1 côté CLI.
PROBLEMS = ('fail', 'missing', 'blocked', 'unavailable')
MAX_STDERR_LINES = 200
HISTORY_VERSION = 1
JOB_ID = re.compile(r'^[0-9a-f]{12}$')
FINISHED = ('done', 'error', 'cancelled')
EVENT_PREFIX = '{"event"'

try:
    from ft_moulinette.report import check_label
except ImportError:  # moteur externe : les libellés restent les identifiants bruts
    check_label = None


class RunError(ValueError):
    """Demande refusée avant mise en file ; le message est destiné à l'utilisateur."""


def _integer(options, name, default, low, high):
    value = options.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RunError(f'« {name} » doit être un entier.')
    if not low <= value <= high:
        raise RunError(f'« {name} » doit être compris entre {low} et {high}.')
    return value


def _flag(options, name):
    value = options.get(name, True)
    if not isinstance(value, bool):
        raise RunError(f'« {name} » doit être un booléen.')
    return value


def validate(payload):
    """Normalise une demande d'exécution ; mêmes contraintes que la CLI."""
    if not isinstance(payload, dict):
        raise RunError('Corps JSON attendu : un objet.')
    target = payload.get('target')
    if not isinstance(target, str) or not target.strip():
        raise RunError('Indiquer le chemin du projet ou du fichier à tester.')
    path = Path(target.strip()).expanduser()
    if not path.is_absolute():
        raise RunError('Le chemin doit être absolu (ou commencer par ~).')
    if not path.exists():
        raise RunError(f'Chemin introuvable : {path}')
    if path.is_file() and path.suffix not in ('.c', '.h'):
        raise RunError('Indiquer un dossier ou un fichier .c/.h existant.')
    if not (path.is_dir() or path.is_file()):
        raise RunError('Indiquer un dossier ou un fichier .c/.h existant.')
    project = payload.get('project', 'auto')
    if project not in PROJECTS:
        raise RunError('Projet attendu : auto, libft ou printf.')
    return dict(
        target=str(path), project=project,
        norm=_flag(payload, 'norm'), memory=_flag(payload, 'memory'), build=_flag(payload, 'build'),
        iterations=_integer(payload, 'iterations', 500, 1, 1_000_000),
        seed=_integer(payload, 'seed', 42, -(2 ** 63), 2 ** 63 - 1),
        timeout=_integer(payload, 'timeout', 15, 1, 3600),
    )


def validate_stored(options):
    """Options relues depuis le disque : même forme qu'à l'envoi, sans exiger que la cible existe encore."""
    if not isinstance(options, dict) or not isinstance(options.get('target'), str):
        raise RunError('options invalides')
    if options.get('project') not in PROJECTS:
        raise RunError('options invalides')
    for name in ('norm', 'memory', 'build'):
        if not isinstance(options.get(name), bool):
            raise RunError('options invalides')
    for name in ('iterations', 'seed', 'timeout'):
        if isinstance(options.get(name), bool) or not isinstance(options.get(name), int):
            raise RunError('options invalides')
    return {key: options[key] for key in
            ('target', 'project', 'norm', 'memory', 'build', 'iterations', 'seed', 'timeout')}


def cli_arguments(options):
    args = [options['target'], '--project', options['project']]
    args += [flag for flag, enabled in (('--no-norm', options['norm']), ('--no-memory', options['memory']),
                                        ('--no-build', options['build'])) if not enabled]
    return args + ['--iterations', str(options['iterations']), '--seed', str(options['seed']),
                   '--timeout', str(options['timeout'])]


def target_root(target):
    target = Path(target)
    return target if target.is_dir() else target.parent


def annotate_row(row, root):
    """Ajoute un libellé lisible et un chemin relatif à la cible."""
    if check_label is not None:
        try:
            row['label'] = check_label(row['check'])
        except Exception:  # un libellé manquant ne doit pas masquer le résultat
            pass
    try:
        row['relative'] = os.path.relpath(row['file'], root)
    except (TypeError, ValueError):
        row['relative'] = row.get('file')
    if not isinstance(row['relative'], str) or row['relative'].startswith('..'):
        row['relative'] = row.get('file')
    return row


def annotate(report, target):
    root = target_root(target)
    for row in report.get('results', []):
        annotate_row(row, root)
    return report


def default_history_path():
    """Fichier d'état propre à l'utilisateur, hors du dépôt (XDG_STATE_HOME)."""
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    return Path(base) / 'ft-moulinette-web' / 'history.json'


def supports_progress(engine, timeout=10):
    """Un moteur plus ancien refuserait --progress : on le détecte via --help."""
    try:
        result = subprocess.run([*engine, '--help'], capture_output=True, text=True, timeout=timeout,
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return '--progress' in result.stdout


class Job:
    def __init__(self, options):
        self.id = uuid.uuid4().hex[:12]
        self.options = options
        self.status = 'queued'
        self.created = time.time()
        self.started = self.finished = None
        self.exit_code = None
        self.report = None
        self.error = None
        self.process = None
        self.cancel_requested = False
        self.partial = []          # résultats problématiques reçus pendant l'exécution
        self.counts = Counter()    # statuts reçus pendant l'exécution

    @classmethod
    def restore(cls, data):
        """Reconstruit une exécution terminée depuis l'historique ; None si l'entrée est invalide."""
        if not isinstance(data, dict) or data.get('status') not in FINISHED:
            return None
        if not isinstance(data.get('id'), str) or not JOB_ID.match(data['id']):
            return None
        options = data.get('options')
        try:
            options = validate_stored(options)
        except RunError:
            return None
        job = cls(options)
        job.id, job.status = data['id'], data['status']
        for name in ('created', 'started', 'finished'):
            value = data.get(name)
            setattr(job, name, value if isinstance(value, (int, float)) and not isinstance(value, bool) else None)
        if job.created is None:
            return None
        job.exit_code = data.get('exit_code') if isinstance(data.get('exit_code'), int) else None
        job.error = data.get('error') if isinstance(data.get('error'), str) else None
        report = data.get('report')
        if isinstance(report, dict) and isinstance(report.get('results'), list):
            job.report = report
        elif job.status == 'done':
            return None
        return job

    def to_dict(self, full=True):
        data = dict(id=self.id, status=self.status, options=self.options, created=self.created,
                    started=self.started, finished=self.finished, exit_code=self.exit_code,
                    error=self.error, command=shlex.join(['ft-moulinette', *cli_arguments(self.options)]))
        if self.status == 'running' or self.counts:
            data['progress'] = dict(count=sum(self.counts.values()), summary=dict(self.counts))
            if full and self.status in ACTIVE:
                data['partial'] = list(self.partial)
        if self.report is not None:
            data['summary'] = self.report.get('summary', {})
            data['module'] = self.report.get('module')
            if full:
                data['report'] = self.report
        return data


class JobManager:
    """Exécute les demandes une par une : chaque exécution est déjà lourde en processus."""

    def __init__(self, engine, grace=5.0, progress=None, history=None):
        self.engine = list(engine)
        self.grace = grace
        self.progress = supports_progress(self.engine) if progress is None else progress
        self.history = Path(history) if history else None
        self.history_error = None
        self.jobs = OrderedDict()
        self._load()
        self.lock = threading.Lock()
        self.wakeup = threading.Condition(self.lock)
        self.closed = False
        self.worker = threading.Thread(target=self._loop, name='ft-moulinette-runs', daemon=True)
        self.worker.start()

    def submit(self, payload):
        options = validate(payload)
        with self.lock:
            if sum(job.status == 'queued' for job in self.jobs.values()) >= MAX_QUEUED:
                raise RunError('Trop d’exécutions en attente ; réessaie plus tard.')
            job = Job(options)
            self.jobs[job.id] = job
            self._trim()
            self.wakeup.notify()
            return job.to_dict()

    def get(self, job_id, full=True):
        with self.lock:
            job = self.jobs.get(job_id)
            return job.to_dict(full) if job else None

    def list(self):
        with self.lock:
            return [job.to_dict(False) for job in reversed(self.jobs.values())]

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            if job.status == 'queued':
                job.status, job.finished = 'cancelled', time.time()
                self._save()
            elif job.status == 'running':
                job.cancel_requested = True
                self._interrupt(job)
            return job.to_dict(False)

    def remove(self, job_id):
        """Retire une exécution terminée de l'historique. None si inconnue, False si encore active."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            if job.status in ACTIVE:
                return False
            del self.jobs[job_id]
            self._save()
            return True

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if job.status == 'queued':
                    job.status, job.finished = 'cancelled', time.time()
                elif job.status == 'running':
                    job.cancel_requested = True
                    self._interrupt(job)
            self.wakeup.notify_all()
        self.worker.join(self.grace + 5)
        with self.lock:
            self._save()

    # --- historique sur disque ---------------------------------------------
    def _load(self):
        if self.history is None or not self.history.exists():
            return
        try:
            data = json.loads(self.history.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            # Fichier illisible : on le garde de côté plutôt que de l'écraser.
            self.history_error = f'Historique illisible ({exc}) ; conservé sous {self.history}.corrompu'
            try:
                os.replace(self.history, self.history.with_name(self.history.name + '.corrompu'))
            except OSError:
                self.history = None
            return
        runs = data.get('runs') if isinstance(data, dict) and data.get('version') == HISTORY_VERSION else None
        jobs = [job for job in map(Job.restore, runs if isinstance(runs, list) else []) if job]
        for job in sorted(jobs, key=lambda j: j.created)[-MAX_HISTORY:]:
            self.jobs[job.id] = job

    def _save(self):
        """Écrit les exécutions terminées de façon atomique ; appelé avec le verrou."""
        if self.history is None:
            return
        runs = [job.to_dict(True) for job in self.jobs.values() if job.status in FINISHED]
        for run in runs:
            run.pop('command', None)
            run.pop('summary', None)
            run.pop('module', None)
            run.pop('progress', None)
        data = json.dumps(dict(version=HISTORY_VERSION, runs=runs), ensure_ascii=False)
        temporary = self.history.with_name(self.history.name + '.tmp')
        try:
            self.history.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.history)
            self.history_error = None
        except OSError as exc:
            self.history_error = f'Historique non enregistré : {exc}'
            try:
                temporary.unlink()
            except OSError:
                pass

    def _trim(self):
        finished = [key for key, job in self.jobs.items() if job.status not in ACTIVE]
        while len(self.jobs) > MAX_HISTORY and finished:
            del self.jobs[finished.pop(0)]

    def _interrupt(self, job):
        # SIGINT laisse le moteur nettoyer ses dossiers temporaires ; SIGKILL en dernier recours.
        process = job.process
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            return

        def force():
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        timer = threading.Timer(self.grace, force)
        timer.daemon = True
        timer.start()

    def _loop(self):
        while True:
            with self.lock:
                job = next((j for j in self.jobs.values() if j.status == 'queued'), None)
                while job is None and not self.closed:
                    self.wakeup.wait()
                    job = next((j for j in self.jobs.values() if j.status == 'queued'), None)
                if job is None:
                    return
                job.status, job.started = 'running', time.time()
                try:
                    job.process = subprocess.Popen(
                        [*self.engine, *cli_arguments(job.options), '--json',
                         *(['--progress'] if self.progress else [])],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                        start_new_session=True)
                except OSError as exc:
                    job.status, job.finished = 'error', time.time()
                    job.error = f'Impossible de lancer le moteur : {exc}'
                    self._save()
                    continue
            stderr = []
            reader = threading.Thread(target=self._read_events, args=(job, stderr), daemon=True)
            reader.start()
            stdout = job.process.stdout.read()
            reader.join()
            job.process.wait()
            job.process.stdout.close()
            job.process.stderr.close()
            with self.lock:
                self._finish(job, job.process.returncode, stdout, '\n'.join(stderr).encode())
                job.process = None
                self._trim()
                self._save()

    def _read_events(self, job, other):
        """Lit stderr ligne à ligne : événements --progress, sinon texte gardé pour le diagnostic."""
        root = target_root(job.options['target'])
        for raw in job.process.stderr:
            line = raw.decode(errors='replace').rstrip('\n')
            event = None
            if line.startswith(EVENT_PREFIX):
                try:
                    event = json.loads(line)
                except ValueError:
                    pass
            row = event.get('result') if isinstance(event, dict) and event.get('event') == 'result' else None
            if not isinstance(row, dict) or 'status' not in row:
                other.append(line)
                del other[:-MAX_STDERR_LINES]
                continue
            with self.lock:
                job.counts[row['status']] += 1
                if row['status'] in PROBLEMS:
                    job.partial.append(annotate_row(row, root))

    def _finish(self, job, code, stdout, stderr):
        job.finished, job.exit_code = time.time(), code
        if job.cancel_requested:
            job.status = 'cancelled'
            return
        text = stderr.decode(errors='replace').strip()
        try:
            report = json.loads(stdout.decode(errors='replace'))
        except ValueError:
            report = None
        if code in (0, 1) and isinstance(report, dict) and 'results' in report:
            job.report = annotate(report, job.options['target'])
            job.status = 'done'
            job.partial = []
            return
        job.status = 'error'
        lines = [line for line in text.splitlines() if line.strip()]
        # argparse termine par « prog: error: message » : ne garder que le message.
        last = lines[-1] if lines else ''
        job.error = last.split('error: ', 1)[-1] if 'error: ' in last else (
            text[-4000:] or f'Le moteur a quitté avec le code {code} sans rapport exploitable.')
