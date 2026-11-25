"""Configuration du service, lue une fois au démarrage. Aucune valeur sensible n'y figure."""
import os
from dataclasses import dataclass
from pathlib import Path

from ft_moulinette_runners.limits import Limits

# Binaire fourni par Google dans les conteneurs Cloud Run dont le sandbox launcher est activé.
GOOGLE_SANDBOX_BIN = '/usr/local/gcp/bin/sandbox'


class SettingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    environment: str
    sandbox_bin: Path
    rootfs: Path
    engine: str          # chemin du lanceur du moteur, vu depuis la sandbox
    python: str          # interpréteur, vu depuis la sandbox
    workspace: Path      # dossier parent des espaces de soumission (côté conteneur parent)
    limits: Limits
    image_version: str
    tests_version: str
    max_cached_results: int = 64

    @classmethod
    def from_env(cls, environ=None):
        environ = os.environ if environ is None else environ
        environment = environ.get('FTM_ENVIRONMENT', 'production')
        if environment not in ('production', 'development', 'test'):
            raise SettingsError('FTM_ENVIRONMENT : production, development ou test.')
        sandbox_bin = environ.get('FTM_SANDBOX_BIN') or GOOGLE_SANDBOX_BIN
        # Un binaire de remplacement (double de test) n'est jamais accepté en production.
        if environment == 'production' and sandbox_bin != GOOGLE_SANDBOX_BIN:
            raise SettingsError('FTM_SANDBOX_BIN ne peut pas être modifié en production.')
        try:
            limits = Limits.from_env(environ)
        except ValueError as exc:
            raise SettingsError(str(exc)) from None
        return cls(
            environment=environment,
            sandbox_bin=Path(sandbox_bin),
            rootfs=Path(environ.get('FTM_SANDBOX_ROOTFS', '/opt/sandbox-rootfs')),
            engine=environ.get('FTM_SANDBOX_ENGINE', '/opt/ft-moulinette/bin/ft-moulinette'),
            python=environ.get('FTM_SANDBOX_PYTHON', '/usr/bin/python3'),
            workspace=Path(environ.get('FTM_WORKSPACE', '/tmp/ftm')),
            limits=limits,
            image_version=environ.get('FTM_IMAGE_VERSION', 'unknown'),
            tests_version=environ.get('FTM_TESTS_VERSION', 'unknown'),
        )
