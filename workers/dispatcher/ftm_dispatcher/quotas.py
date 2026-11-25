"""Quotas applicatifs (AGENT.md §19), réservés atomiquement avant la mise en file.

Ils limitent l'usage et le coût mais ne garantissent pas l'absence de frais Google : ce n'est qu'un
plafond applicatif, à compléter par des alertes budgétaires (docs/cloudrun-costs.md).
"""
import os
import threading
import time
from dataclasses import dataclass


class QuotaExceeded(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class QuotaPolicy:
    per_user_daily: int = 20
    per_user_concurrent: int = 1    # soumissions en file ou en cours par utilisateur
    global_daily: int = 300         # plafond applicatif global (interrupteur de coût)
    max_in_flight: int = 20         # file bornée : soumissions en file ou en cours, tous utilisateurs
    min_interval_seconds: int = 10  # limite les tentatives répétées
    reservation_ttl: int = 1800     # une réservation perdue (worker tué) expire d'elle-même
    # La concurrence d'exécution (2 par défaut) est le nombre de workers RQ : MAX_CONCURRENT_JOBS.

    @classmethod
    def from_env(cls, environ=None):
        environ = os.environ if environ is None else environ
        names = {'per_user_daily': 'FTM_QUOTA_USER_DAILY', 'per_user_concurrent': 'FTM_QUOTA_USER_CONCURRENT',
                 'global_daily': 'FTM_QUOTA_GLOBAL_DAILY', 'max_in_flight': 'FTM_QUOTA_MAX_IN_FLIGHT',
                 'min_interval_seconds': 'FTM_QUOTA_MIN_INTERVAL'}
        values = {}
        for field, variable in names.items():
            raw = environ.get(variable)
            if raw:
                if not raw.isdigit() or (int(raw) == 0 and field != 'min_interval_seconds'):
                    raise ValueError(f'{variable} doit être un entier positif')
                values[field] = int(raw)
        return cls(**values)


def _day(now):
    return time.strftime('%Y%m%d', time.gmtime(now))


# Réservation atomique : refuse sans rien modifier si une limite est atteinte.
# KEYS : 1 compteur jour utilisateur, 2 compteur jour global, 3 actifs utilisateur (zset),
#        4 actifs globaux (zset), 5 cooldown utilisateur
# ARGV : 1 id soumission, 2 maintenant, 3 ttl réservation, 4 quota jour utilisateur, 5 quota jour global,
#        6 en cours par utilisateur, 7 en cours au total (file bornée), 8 intervalle minimal
RESERVE_LUA = """
local now = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now - tonumber(ARGV[3]))
redis.call('ZREMRANGEBYSCORE', KEYS[4], '-inf', now - tonumber(ARGV[3]))
if redis.call('ZCARD', KEYS[4]) >= tonumber(ARGV[7]) then return 'queue_full' end
if tonumber(ARGV[8]) > 0 and redis.call('EXISTS', KEYS[5]) == 1 then return 'too_soon' end
if tonumber(redis.call('GET', KEYS[1]) or '0') >= tonumber(ARGV[4]) then return 'user_daily' end
if tonumber(redis.call('GET', KEYS[2]) or '0') >= tonumber(ARGV[5]) then return 'global_daily' end
if redis.call('ZCARD', KEYS[3]) >= tonumber(ARGV[6]) then return 'user_concurrent' end
redis.call('INCR', KEYS[1]); redis.call('EXPIRE', KEYS[1], 172800)
redis.call('INCR', KEYS[2]); redis.call('EXPIRE', KEYS[2], 172800)
redis.call('ZADD', KEYS[3], now, ARGV[1]); redis.call('EXPIRE', KEYS[3], tonumber(ARGV[3]))
redis.call('ZADD', KEYS[4], now, ARGV[1]); redis.call('EXPIRE', KEYS[4], tonumber(ARGV[3]))
if tonumber(ARGV[8]) > 0 then redis.call('SET', KEYS[5], '1', 'EX', tonumber(ARGV[8])) end
return 'ok'
"""

MESSAGES = {
    'queue_full': 'File d’attente pleine : réessaie dans quelques minutes.',
    'too_soon': 'Soumissions trop rapprochées : patiente quelques secondes.',
    'user_daily': 'Quota quotidien de soumissions atteint.',
    'global_daily': 'Plafond quotidien global atteint : exécutions suspendues jusqu’à demain (UTC).',
    'user_concurrent': 'Une soumission est déjà en cours pour ce compte.',
}


class RedisQuotas:
    """Quotas stockés dans Redis (clés préfixées ftm:quota:). user_key : identifiant opaque côté VPS."""

    def __init__(self, redis, policy=None, prefix='ftm:quota:', clock=time.time):
        self.redis = redis
        self.policy = policy or QuotaPolicy()
        self.prefix = prefix
        self.clock = clock
        self._script = redis.register_script(RESERVE_LUA)

    def _keys(self, user_key, now):
        day, p = _day(now), self.prefix
        return [f'{p}user:{user_key}:day:{day}', f'{p}global:day:{day}', f'{p}user:{user_key}:active',
                f'{p}global:active', f'{p}user:{user_key}:cooldown']

    def reserve(self, user_key, submission_id):
        now, policy = self.clock(), self.policy
        answer = self._script(keys=self._keys(user_key, now), args=[
            submission_id, now, policy.reservation_ttl, policy.per_user_daily, policy.global_daily,
            policy.per_user_concurrent, policy.max_in_flight, policy.min_interval_seconds])
        answer = answer.decode() if isinstance(answer, bytes) else answer
        if answer != 'ok':
            raise QuotaExceeded(answer, MESSAGES[answer])

    def release(self, user_key, submission_id):
        keys = self._keys(user_key, self.clock())
        self.redis.zrem(keys[2], submission_id)
        self.redis.zrem(keys[3], submission_id)

    def usage(self):
        now = self.clock()
        return dict(global_today=int(self.redis.get(f'{self.prefix}global:day:{_day(now)}') or 0),
                    in_flight=int(self.redis.zcard(f'{self.prefix}global:active')),
                    policy=self.policy.__dict__)


class MemoryQuotas:
    """Même politique en mémoire, pour les tests et le développement mono-processus."""

    def __init__(self, policy=None, clock=time.time):
        self.policy = policy or QuotaPolicy()
        self.clock = clock
        self.daily, self.active, self.cooldown = {}, {}, {}
        self._lock = threading.Lock()

    def reserve(self, user_key, submission_id):
        with self._lock:
            now, policy, day = self.clock(), self.policy, _day(self.clock())
            for key in list(self.active):
                if now - self.active[key][1] > policy.reservation_ttl:
                    del self.active[key]
            user_active = sum(1 for user, _ in self.active.values() if user == user_key)
            checks = [
                ('queue_full', len(self.active) >= policy.max_in_flight),
                ('too_soon', policy.min_interval_seconds and now < self.cooldown.get(user_key, 0)),
                ('user_daily', self.daily.get((user_key, day), 0) >= policy.per_user_daily),
                ('global_daily', self.daily.get(('*', day), 0) >= policy.global_daily),
                ('user_concurrent', user_active >= policy.per_user_concurrent),
            ]
            for code, refused in checks:
                if refused:
                    raise QuotaExceeded(code, MESSAGES[code])
            for key in ((user_key, day), ('*', day)):
                self.daily[key] = self.daily.get(key, 0) + 1
            self.active[submission_id] = (user_key, now)
            self.cooldown[user_key] = now + policy.min_interval_seconds

    def release(self, user_key, submission_id):
        with self._lock:
            self.active.pop(submission_id, None)

    def usage(self):
        day = _day(self.clock())
        return dict(global_today=self.daily.get(('*', day), 0), in_flight=len(self.active), policy=self.policy.__dict__)
