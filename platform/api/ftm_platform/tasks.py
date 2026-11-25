"""Tâches du worker de la plateforme (RQ). Le worker est le seul composant du VPS qui détient
l'identité Google ; il ne compile ni n'exécute rien et délègue au moteur configuré (cloudrun en production).
"""
import logging
import os
import time
from datetime import timedelta

from sqlalchemy import select, update

from ft_moulinette_runners.base import INFRASTRUCTURE_OUTCOMES
from ft_moulinette_runners.config import limits_from_env
from ftm_dispatcher import tasks as dispatcher

from .db import session_factory, transaction
from .models import FINISHED, Submission, now
from .runtime import Runtime
from .settings import database_url

log = logging.getLogger('ft_moulinette.platform.worker')
# Ces résultats ne disent rien du code soumis : la soumission est marquée « failed » (erreur d'infrastructure).
FAILED_OUTCOMES = set(INFRASTRUCTURE_OUTCOMES) | {'cancelled'}


def _context():
    return session_factory(database_url()), Runtime(os.environ['REDIS_URL'])


def _set_status(factory, submission_id, status):
    with transaction(factory) as session:
        session.execute(update(Submission).where(Submission.id == submission_id,
                                                 Submission.status.not_in(FINISHED)).values(status=status))


def _finish(factory, submission_id, result):
    outcome = result['outcome']
    metadata = result.get('metadata') or {}
    with transaction(factory) as session:
        submission = session.get(Submission, submission_id, with_for_update=True)
        if submission is None:
            return
        submission.status = 'failed' if outcome in FAILED_OUTCOMES else 'done'
        submission.outcome = outcome
        submission.report = result.get('report')
        submission.error = result.get('error')
        submission.result_metadata = metadata
        submission.backend = metadata.get('backend')
        submission.finished_at = now()
        submission.duration_seconds = metadata.get('duration_seconds') or (
            (submission.finished_at - submission.started_at).total_seconds() if submission.started_at else None)
        submission.archive = None  # le code soumis n'est pas conservé après exécution


def run_submission(submission_id):
    """Exécute une soumission en file. Sans effet si elle n'est plus « queued » (déjà prise ou annulée)."""
    factory, runtime = _context()
    with transaction(factory) as session:
        submission = session.get(Submission, submission_id, with_for_update=True)
        if submission is None or submission.status != 'queued':
            log.warning('submission=%s ignorée (absente ou déjà prise)', submission_id)
            return
        submission.status, submission.started_at = 'preparing', now()
        job = dict(project=submission.project, archive=submission.archive, options=submission.options,
                   target=submission.target, user_key=str(submission.user_id))
    if not runtime.executions_enabled():
        runtime.quotas.release(job['user_key'], submission_id)
        _finish(factory, submission_id, dict(outcome='infrastructure_error', report=None, metadata={},
                                              error=dict(category='infrastructure', code='disabled',
                                                         message='Exécutions désactivées par l’administrateur.')))
        return
    result = dispatcher.execute_submission(
        submission_id, job['project'], job['archive'], options=job['options'], target=job['target'],
        user_key=job['user_key'], quotas=runtime.quotas,
        on_status=lambda stage: _set_status(factory, submission_id, stage))
    _finish(factory, submission_id, result)
    return result['outcome']


def check_runner():
    """Disponibilité du moteur (Cloud Run en production), mesurée avec l'identité du worker."""
    factory, runtime = _context()
    started = time.time()
    data = dict(checked_at=started, backend=None, available=False, detail='', capabilities=None)
    try:
        engine = dispatcher.backend()
        data['backend'] = engine.name
        health = engine.check()
        data.update(available=health.available, detail=health.detail)
        if health.available:
            capabilities = engine.capabilities()
            data['capabilities'] = {k: capabilities.get(k) for k in
                                    ('protocol', 'image_version', 'tests_version', 'isolated', 'network', 'analyzers')}
    except Exception as exc:  # configuration, authentification, réseau : jamais « disponible »
        data['detail'] = getattr(exc, 'message', None) or type(exc).__name__
    data['latency_seconds'] = round(time.time() - started, 3)
    runtime.store_runner_health(data)
    data['reaped'] = reap_stale(factory, runtime)
    return data


def reap_stale(factory=None, runtime=None, grace_seconds=600):
    """Soumissions bloquées (worker arrêté en cours d'exécution) : marquées en échec, jamais relancées."""
    if factory is None:
        factory, runtime = _context()
    limit = limits_from_env().request_timeout + grace_seconds
    cutoff = now() - timedelta(seconds=limit)
    reaped = []
    with transaction(factory) as session:
        stale = session.scalars(select(Submission).where(
            Submission.status.in_(('preparing', 'running', 'analyzing')), Submission.started_at < cutoff
        ).with_for_update()).all()
        for submission in stale:
            submission.status, submission.outcome, submission.finished_at = 'failed', 'infrastructure_error', now()
            submission.error = dict(category='infrastructure', code='unknown_state',
                                    message='Exécution interrompue (worker arrêté) : état réel inconnu. '
                                            'Relance la soumission si besoin.')
            submission.archive = None
            reaped.append((submission.id, str(submission.user_id)))
    for submission_id, user_key in reaped:
        runtime.quotas.release(user_key, submission_id)
    return [submission_id for submission_id, _ in reaped]
