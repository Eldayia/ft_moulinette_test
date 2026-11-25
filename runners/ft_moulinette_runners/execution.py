"""Lancement borné du moteur et interprétation de sa sortie.

Partagé par LocalRunner (moteur lancé directement) et par le runner Cloud Run (moteur lancé par
`sandbox do`) : mêmes arguments, mêmes bornes, même interprétation, aucun test dupliqué.
"""
import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field

from .base import ExecutionResult, infrastructure_error, user_error
from .protocol import analyzers, classify, relativize_report, validate_report

EVENT_PREFIX = b'{"event"'


def engine_arguments(target, project, options, command_timeout):
    """Arguments de la CLI ft-moulinette. Seules des options validées y figurent, jamais d'entrée libre."""
    args = [str(target), '--project', project, '--json', '--progress',
            '--iterations', str(options.iterations), '--seed', str(options.seed), '--timeout', str(command_timeout)]
    for flag, enabled in (('--no-norm', options.norm), ('--no-memory', options.memory), ('--no-build', options.build)):
        if not enabled:
            args.append(flag)
    return args


@dataclass
class ProcessOutcome:
    returncode: int = None
    stdout: bytes = b''
    stderr_text: str = ''
    timed_out: bool = False
    cancelled: bool = False
    stdout_overflow: bool = False
    duration: float = 0.0
    events: int = 0
    started: float = field(default_factory=time.monotonic)


class BoundedProcess:
    """Sous-processus dans sa propre session, sorties bornées, délai global et annulation."""

    def __init__(self, command, deadline, max_stdout, max_log, on_event=None, grace=5.0, env=None):
        self.command = list(command)
        self.deadline = deadline
        self.max_stdout = max_stdout
        self.max_log = max_log
        self.on_event = on_event
        self.grace = grace
        self.env = env
        self.process = None
        self.outcome = ProcessOutcome()
        self._lock = threading.Lock()
        self._stopping = False

    def run(self):
        outcome = self.outcome
        try:
            self.process = subprocess.Popen(self.command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, start_new_session=True, env=self.env)
        except OSError as exc:
            raise infrastructure_error('engine_unavailable', f'Impossible de lancer le moteur : {exc}') from None
        readers = [threading.Thread(target=self._read_stdout, daemon=True),
                   threading.Thread(target=self._read_stderr, daemon=True)]
        for reader in readers:
            reader.start()
        try:
            self.process.wait(timeout=self.deadline)
        except subprocess.TimeoutExpired:
            outcome.timed_out = True
            self.stop()
        for reader in readers:
            reader.join(self.grace + 5)
        self.process.wait()
        self.process.stdout.close()
        self.process.stderr.close()
        outcome.returncode = self.process.returncode
        outcome.duration = time.monotonic() - outcome.started
        return outcome

    def stop(self, cancelled=False):
        """SIGINT au groupe (le moteur nettoie ses dossiers), SIGKILL après le délai de grâce."""
        with self._lock:
            if cancelled:
                self.outcome.cancelled = True
            if self._stopping or self.process is None:
                return
            self._stopping = True
        process = self.process
        for number, wait in ((signal.SIGINT, self.grace), (signal.SIGKILL, None)):
            try:
                os.killpg(process.pid, number)
            except ProcessLookupError:
                return
            try:
                process.wait(timeout=wait)
                return
            except subprocess.TimeoutExpired:
                continue

    def _read_stdout(self):
        chunks, size = [], 0
        for chunk in iter(lambda: self.process.stdout.read(65536), b''):
            if size + len(chunk) > self.max_stdout:
                self.outcome.stdout_overflow = True
                self.stop()
                break
            chunks.append(chunk)
            size += len(chunk)
        self.outcome.stdout = b''.join(chunks)

    def _read_stderr(self):
        kept, size = [], 0
        for line in self.process.stderr:
            if line.startswith(EVENT_PREFIX):
                self.outcome.events += 1
                if self.on_event is not None:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        event = None
                    if isinstance(event, dict) and event.get('event') == 'result' and isinstance(event.get('result'), dict):
                        try:
                            self.on_event(event['result'])
                        except Exception:  # un consommateur défaillant n'interrompt pas l'exécution
                            pass
                continue
            if size < self.max_log:
                kept.append(line[: self.max_log - size])
                size += len(kept[-1])
        self.outcome.stderr_text = b''.join(kept).decode(errors='replace')


def _argparse_message(text):
    lines = [line for line in text.splitlines() if line.strip()]
    last = lines[-1] if lines else ''
    return last.split('error: ', 1)[-1] if 'error: ' in last else (text[-2000:] or 'Erreur du moteur.')


def interpret(submission, process, limits, backend, root=None, extra_metadata=None):
    """Transforme la sortie du moteur en ExecutionResult. Sans rapport valide : jamais de succès."""
    metadata = dict(backend=backend, duration_seconds=round(process.duration, 3), progress_events=process.events,
                    interruption=None, **(extra_metadata or {}))

    def failed(outcome, error):
        metadata['interruption'] = error.code
        return ExecutionResult(submission.submission_id, outcome, None, metadata, error)

    if process.cancelled:
        return failed('cancelled', infrastructure_error('cancelled', 'Exécution annulée.'))
    if process.timed_out:
        return failed('timeout', infrastructure_error(
            'timeout', f'Délai global de {limits.submission_timeout} s dépassé ; exécution arrêtée.'))
    if process.stdout_overflow:
        return failed('resource_limit', infrastructure_error(
            'output_limit', f'Rapport supérieur à {limits.max_report_bytes} octets ; exécution arrêtée.'))
    if process.returncode == 2:
        return failed('unsupported', user_error('rejected_by_engine', _argparse_message(process.stderr_text)))
    if process.returncode not in (0, 1):
        return failed('infrastructure_error', infrastructure_error(
            'engine_failed', f'Le moteur a quitté avec le code {process.returncode} sans rapport exploitable.'))
    try:
        report = json.loads(process.stdout.decode('utf-8'))
        validate_report(report, submission.project, limits)
    except (ValueError, UnicodeDecodeError) as exc:
        return failed('infrastructure_error', infrastructure_error('invalid_report', f'Rapport invalide : {exc}'))
    if root is not None:
        relativize_report(report, root)
    used, unavailable = analyzers(report, submission.options)
    metadata.update(analyzers_used=used, analyzers_unavailable=unavailable)
    return ExecutionResult(submission.submission_id, classify(report), report, metadata, None)
