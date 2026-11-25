"""Sélection explicite du moteur d'exécution par configuration.

Aucun repli : si le moteur demandé ne peut pas être construit, c'est une erreur. En production
(FTM_ENVIRONMENT=production), seul un moteur isolé est accepté ; local, docker et mock sont refusés.
"""
import os

from .limits import Limits

BACKENDS = ('local', 'docker', 'cloudrun', 'mock')
TRUE = ('1', 'true', 'yes', 'on')


class ConfigurationError(RuntimeError):
    pass


def is_production(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('FTM_ENVIRONMENT', 'development') == 'production'


def executions_enabled(environ=None):
    """Interrupteur administrateur : FTM_EXECUTIONS_DISABLED=1 bloque toute nouvelle exécution."""
    environ = os.environ if environ is None else environ
    return environ.get('FTM_EXECUTIONS_DISABLED', '').lower() not in TRUE


def limits_from_env(environ=None):
    environ = os.environ if environ is None else environ
    values = dict(environ)
    if environ.get('EXECUTION_TIMEOUT') and not environ.get('FTM_LIMIT_SUBMISSION_TIMEOUT'):
        values['FTM_LIMIT_SUBMISSION_TIMEOUT'] = environ['EXECUTION_TIMEOUT']
    try:
        return Limits.from_env(values)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from None


def backend_from_env(environ=None, **overrides):
    environ = os.environ if environ is None else environ
    name = environ.get('EXECUTION_BACKEND', '').strip()
    if name not in BACKENDS:
        raise ConfigurationError(f'EXECUTION_BACKEND doit valoir {", ".join(BACKENDS)} (reçu : {name!r}).')
    if is_production(environ) and name != 'cloudrun':
        raise ConfigurationError(f'Moteur « {name} » refusé en production : seul « cloudrun » isole le code soumis.')
    limits = limits_from_env(environ)
    if name == 'local':
        from .local import LocalRunner
        return LocalRunner(limits=limits, **overrides)
    if name == 'mock':
        from .mock import MockRunner
        return MockRunner(**overrides)
    if name == 'docker':
        raise ConfigurationError('DockerRunner n’est pas encore disponible (phase 3 de docs/cloudrun.md).')
    url = environ.get('CLOUD_RUN_URL', '').strip()
    if not url.startswith('https://'):
        raise ConfigurationError('CLOUD_RUN_URL doit être l’URL https:// du service runner-api.')
    mode = environ.get('GCP_AUTH_MODE', 'key')
    account = environ.get('GCP_INVOKER_SERVICE_ACCOUNT') or None
    if mode == 'key' and not environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        raise ConfigurationError('GCP_AUTH_MODE=key exige GOOGLE_APPLICATION_CREDENTIALS (secret gcp_invoker).')
    if mode == 'wif' and not account:
        raise ConfigurationError('GCP_AUTH_MODE=wif exige GCP_INVOKER_SERVICE_ACCOUNT.')
    from .cloudrun import CloudRunRunner, IdTokenProvider
    try:
        tokens = IdTokenProvider(environ.get('CLOUD_RUN_AUDIENCE') or url, mode, account)
        backend = CloudRunRunner(url, tokens, limits, **overrides)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from None
    if is_production(environ) and not backend.isolated:
        raise ConfigurationError('Moteur non isolé refusé en production.')
    return backend
