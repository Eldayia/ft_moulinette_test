"""Configuration de la plateforme, lue dans l'environnement. Aucun secret Google ici : l'API publique n'en a pas."""
import os
from dataclasses import dataclass


class SettingsError(RuntimeError):
    pass


def database_url(environ=None):
    """DATABASE_URL, avec le mot de passe lu dans DATABASE_PASSWORD_FILE (secret Docker) si fourni.

    Dans ce cas, DATABASE_URL contient le marqueur {password}, remplacé (encodé) à la lecture.
    """
    from urllib.parse import quote
    environ = os.environ if environ is None else environ
    url = environ.get('DATABASE_URL', '')
    secret = environ.get('DATABASE_PASSWORD_FILE')
    if secret:
        with open(secret, encoding='utf-8') as handle:
            password = handle.read().strip()
        if '{password}' not in url:
            raise SettingsError('DATABASE_URL doit contenir {password} quand DATABASE_PASSWORD_FILE est utilisé.')
        url = url.replace('{password}', quote(password, safe=''))
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    public_origin: str          # ex. https://moulinette.example : seule origine admise pour les écritures
    cookie_secure: bool
    session_hours: int
    trust_proxy: bool           # True derrière Nginx Proxy Manager : X-Forwarded-For fiable (dernier saut)
    cost_per_second: float      # estimation affichée aux administrateurs (0 = non configurée)
    environment: str

    @classmethod
    def from_env(cls, environ=None):
        environ = os.environ if environ is None else environ
        db_url = database_url(environ)
        if not db_url.startswith('postgresql'):
            raise SettingsError('DATABASE_URL doit désigner PostgreSQL (postgresql+psycopg://…).')
        redis_url = environ.get('REDIS_URL', '')
        if not redis_url.startswith(('redis://', 'rediss://', 'unix://')):
            raise SettingsError('REDIS_URL manquante.')
        origin = environ.get('FTM_PUBLIC_ORIGIN', '').rstrip('/')
        environment = environ.get('FTM_ENVIRONMENT', 'production')
        if environment == 'production' and not origin.startswith('https://'):
            raise SettingsError('FTM_PUBLIC_ORIGIN doit être une origine https:// en production.')
        try:
            hours = int(environ.get('FTM_SESSION_HOURS', '12'))
            cost = float(environ.get('FTM_COST_PER_SECOND', '0') or 0)
        except ValueError:
            raise SettingsError('FTM_SESSION_HOURS et FTM_COST_PER_SECOND doivent être numériques.') from None
        if not 1 <= hours <= 24 * 30 or cost < 0:
            raise SettingsError('Durée de session ou coût hors limites.')
        return cls(database_url=db_url, redis_url=redis_url, public_origin=origin,
                   cookie_secure=environ.get('FTM_COOKIE_SECURE', '1') != '0' or environment == 'production',
                   session_hours=hours, trust_proxy=environ.get('FTM_TRUST_PROXY', '0') == '1',
                   cost_per_second=cost, environment=environment)
