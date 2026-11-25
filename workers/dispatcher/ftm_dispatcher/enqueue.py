"""Mise en file d'une soumission depuis l'API du VPS (Redis/RQ).

Ordre : interrupteur, validation complète de l'archive (sur le VPS, sans rien exécuter), quotas réservés
atomiquement, puis mise en file unique par submission_id (déduplication RQ atomique).
"""
from ft_moulinette_runners.base import Submission, user_error
from ft_moulinette_runners.config import executions_enabled, limits_from_env
from ft_moulinette_runners.workspace import read_archive

from .quotas import QuotaExceeded
from .tasks import execute_submission

QUEUE_NAME = 'ftm-submissions'


class SubmissionRefused(Exception):
    def __init__(self, code, message, category='user'):
        super().__init__(message)
        self.code, self.message, self.category = code, message, category


def enqueue_submission(queue, submission: Submission, user_key, quotas, limits=None):
    """Retourne le job RQ. Lève SubmissionRefused (motif destiné à l'utilisateur) sinon."""
    if not executions_enabled():
        raise SubmissionRefused('maintenance', 'Exécutions suspendues pour maintenance.', 'infrastructure')
    if submission.archive is None:
        raise user_error('unsupported_source', 'Une archive est requise pour une exécution distante.')
    limits = limits or limits_from_env()
    read_archive(submission.archive, limits)  # lève ExecutionError(user) pour toute archive dangereuse
    if queue.fetch_job(submission.submission_id) is not None:  # avant réservation : ne pas toucher à l'original
        raise SubmissionRefused('duplicate', 'Cette soumission est déjà en file ou traitée.')
    try:
        quotas.reserve(user_key, submission.submission_id)
    except QuotaExceeded as exc:
        raise SubmissionRefused(exc.code, exc.message) from None
    from rq.exceptions import DuplicateJobError
    try:
        return queue.enqueue_call(
            execute_submission, job_id=submission.submission_id, unique=True,
            kwargs=dict(submission_id=submission.submission_id, project=submission.project,
                        archive=submission.archive, options=submission.options.to_dict(),
                        target=submission.target, tests_version=submission.tests_version, user_key=user_key),
            timeout=limits.request_timeout + 60, result_ttl=7 * 86400, failure_ttl=7 * 86400, retry=None,
            description=f'ft-moulinette {submission.project}')
    except DuplicateJobError:
        # Course avec un envoi identique : la réservation (même identifiant) appartient à l'original.
        raise SubmissionRefused('duplicate', 'Cette soumission est déjà en file ou traitée.') from None
    except Exception:
        quotas.release(user_key, submission.submission_id)
        raise

