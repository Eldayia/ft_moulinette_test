"""Exécution d'une soumission dans une sandbox Cloud Run neuve, via la CLI officielle `sandbox`.

Seules les options documentées (docs.cloud.google.com/run/docs/reference/sandbox-cli) sont utilisées :
`do`, `--sandbox-name`, `--rootfs`, `--stdin=false`, `--mount type=bind,src=…,dst=…,readonly`, `--env`,
`--workdir`, puis `delete --force`. Jamais `--allow-egress`, jamais `--write`, jamais de montage en écriture.

Ce module ne compile ni n'exécute rien lui-même : tout ce qui touche au contenu soumis (préprocesseur,
make, binaires, Norminette, Valgrind) se déroule dans la sandbox, à partir du système de fichiers
`sandbox-c` copié dans l'image sous `FTM_SANDBOX_ROOTFS`.
"""
import os
import shutil
import subprocess
import time

from ft_moulinette_runners.base import ExecutionResult, Submission, infrastructure_error, user_error
from ft_moulinette_runners.execution import BoundedProcess, engine_arguments, interpret
from ft_moulinette_runners.workspace import extract_archive

from .logs import log

MOUNT_POINT = '/submission'
SANDBOX_ENV = ('PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=/tmp', 'TMPDIR=/tmp', 'LANG=C.UTF-8')


class SandboxExecutor:
    def __init__(self, settings, grace=5.0):
        self.settings = settings
        self.grace = grace

    # --- disponibilité -------------------------------------------------------
    def readiness(self):
        """(prêt, détail). Échec fermé : sans sandbox utilisable, aucune exécution n'est acceptée."""
        s = self.settings
        if not s.sandbox_bin.is_file() or not os.access(s.sandbox_bin, os.X_OK):
            return False, f'CLI sandbox absente ({s.sandbox_bin}) : sandbox launcher non activé ?'
        if not s.rootfs.is_dir():
            return False, f'Système de fichiers de la sandbox absent ({s.rootfs}).'
        for inner in (s.engine, s.python):
            if not (s.rootfs / inner.lstrip('/')).exists():
                return False, f'{inner} absent du système de fichiers de la sandbox.'
        try:
            s.workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            return False, f'Espace de travail inutilisable : {exc.strerror}.'
        return True, 'Sandbox prête.'

    # --- commande ---------------------------------------------------------------
    def command(self, name, input_dir, target, project, options, limits):
        s = self.settings
        command = [str(s.sandbox_bin), 'do', '--sandbox-name', name, '--rootfs', str(s.rootfs), '--stdin=false',
                   '--mount', f'type=bind,src={input_dir},dst={MOUNT_POINT},readonly', '--workdir', '/tmp']
        for variable in SANDBOX_ENV:
            command += ['--env', variable]
        return command + ['--', s.python, s.engine, *engine_arguments(target, project, options, limits.command_timeout)]

    def delete(self, name):
        """Suppression systématique. `delete --force` sort en 1 si la sandbox n'existe plus (déjà supprimée)."""
        try:
            completed = subprocess.run([str(self.settings.sandbox_bin), 'delete', '--force', name],
                                       stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f'delete_failed:{type(exc).__name__}'
        return 'deleted' if completed.returncode == 0 else 'absent_after_run'

    # --- exécution --------------------------------------------------------------
    def execute(self, fields, archive, limits):
        sid = fields['submission_id']
        submission = Submission(fields['project'], archive=archive, options=fields['options'], target=fields['target'],
                                tests_version=fields['tests_version'], submission_id=sid, limits=limits)
        metadata = dict(engine_version=self.settings.tests_version, tests_version=self.settings.tests_version,
                        image_version=self.settings.image_version, isolated=True,
                        compile_seconds=None, tests_seconds=None)  # non mesurées séparément par le moteur
        ready, detail = self.readiness()
        if not ready:
            log('ERROR', 'sandbox indisponible', submission_id=sid, detail=detail, error_code='sandbox_unavailable')
            return ExecutionResult(sid, 'sandbox_unavailable', None, dict(metadata, backend='cloudrun',
                                   sandbox_status='unavailable', interruption='sandbox_unavailable'),
                                   infrastructure_error('sandbox_unavailable', detail))
        workspace = self.settings.workspace / sid
        try:
            workspace.mkdir(mode=0o700)
        except FileExistsError:
            raise user_error('duplicate_submission', 'Soumission déjà en cours sur ce runner.') from None
        name = f'ftm-{sid}'
        sandbox_status = 'not_started'
        started = time.monotonic()
        try:
            input_dir = workspace / 'input'
            input_dir.mkdir(mode=0o755)
            extract_archive(archive, input_dir, limits)
            target = MOUNT_POINT
            if fields['target']:
                if not (input_dir / fields['target']).is_file():
                    raise user_error('invalid_path', f'Fichier ciblé absent de la soumission : {fields["target"]}')
                target = f'{MOUNT_POINT}/{fields["target"]}'
            process = BoundedProcess(self.command(name, input_dir, target, fields['project'], fields['options'], limits),
                                     limits.submission_timeout, limits.max_report_bytes, limits.max_log_bytes,
                                     None, self.grace, env={'PATH': '/usr/bin:/bin'})
            sandbox_status = 'started'
            outcome = process.run()
        finally:
            if sandbox_status == 'started':
                sandbox_status = self.delete(name)
            shutil.rmtree(workspace, ignore_errors=True)
        metadata.update(sandbox_status=sandbox_status, total_seconds=round(time.monotonic() - started, 3))
        result = interpret(submission, outcome, limits, 'cloudrun', MOUNT_POINT, metadata)
        if result.outcome == 'infrastructure_error' and outcome.stderr_text:
            # La CLI sandbox signale ses propres erreurs sur stderr ; seule une courte fin est journalisée.
            log('ERROR', 'échec de la sandbox', submission_id=sid, detail=outcome.stderr_text[-400:],
                error_code=result.error.code if result.error else None)
        return result
