"""Tâche exécutée par le worker RQ du VPS. Elle ne compile ni n'exécute rien : elle délègue au moteur
configuré (EXECUTION_BACKEND=cloudrun en production) et renvoie un résultat sérialisable.

Aucune nouvelle tentative automatique : si l'état réel d'une soumission est inconnu, le résultat le dit
et c'est à l'utilisateur de relancer (nouvel identifiant). Aucun repli vers une exécution sur le VPS.
"""
import logging
import os
import threading

from ft_moulinette_runners.base import ExecutionError, ExecutionResult, Options, Submission
from ft_moulinette_runners.config import ConfigurationError, backend_from_env, executions_enabled

log = logging.getLogger('ft_moulinette.dispatcher')
_backend = None
_backend_lock = threading.Lock()


def backend():
    """Moteur construit une fois par processus worker, à partir de l'environnement."""
    global _backend
    with _backend_lock:
        if _backend is None:
            _backend = backend_from_env()
        return _backend


def _quotas():
    url = os.environ.get('REDIS_URL')
    if not url:
        return None
    import redis
    from .quotas import QuotaPolicy, RedisQuotas
    return RedisQuotas(redis.Redis.from_url(url), QuotaPolicy.from_env())


def execute_submission(submission_id, project, archive, options=None, target=None, tests_version=None,
                       user_key=None, quotas=None):
    """Point d'entrée RQ. Retourne toujours un dict au format ExecutionResult.to_dict()."""
    quotas = quotas if quotas is not None else (_quotas() if user_key else None)
    try:
        if not executions_enabled():
            error = ExecutionError('infrastructure', 'disabled', 'Exécutions désactivées par l’administrateur.')
            return ExecutionResult(submission_id, 'infrastructure_error', None, dict(backend='none'), error).to_dict()
        try:
            engine = backend()
        except ConfigurationError as exc:
            log.error('submission=%s configuration invalide : %s', submission_id, exc)
            error = ExecutionError('infrastructure', 'configuration', 'Moteur d’exécution mal configuré.')
            return ExecutionResult(submission_id, 'infrastructure_error', None, dict(backend='none'), error).to_dict()
        try:
            submission = Submission(project, archive=archive, options=Options.from_dict(options), target=target,
                                    tests_version=tests_version, submission_id=submission_id)
            result = engine.execute(submission)
        except ExecutionError as exc:
            outcome = 'unsupported' if exc.category == 'user' else 'infrastructure_error'
            result = ExecutionResult(submission_id, outcome, None, dict(backend=engine.name), exc)
        log.info('submission=%s backend=%s outcome=%s error=%s', submission_id, engine.name, result.outcome,
                 result.error.code if result.error else '-')
        return result.to_dict()
    finally:
        if quotas is not None and user_key:
            quotas.release(user_key, submission_id)
