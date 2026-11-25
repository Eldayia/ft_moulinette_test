"""Redis, file RQ, quotas et interrupteur administrateur, partagés par l'API et le worker."""
import json
import time

import redis as redis_lib
from rq import Queue

from ft_moulinette_runners.config import executions_enabled
from ftm_dispatcher.quotas import QuotaPolicy, RedisQuotas

QUEUE_NAME = 'ftm-submissions'
SWITCH_KEY = 'ftm:admin:executions_disabled'
RUNNER_HEALTH_KEY = 'ftm:runner:health'
LOGIN_ATTEMPTS = 'ftm:login:'


class Runtime:
    def __init__(self, redis_url, policy=None):
        self.redis = redis_lib.Redis.from_url(redis_url)
        self.queue = Queue(QUEUE_NAME, connection=self.redis)
        self.quotas = RedisQuotas(self.redis, policy or QuotaPolicy.from_env())

    # --- interrupteur : variable d'environnement OU drapeau Redis (effet immédiat, sans redémarrage) ---
    def executions_enabled(self):
        return executions_enabled() and not self.redis.exists(SWITCH_KEY)

    def set_executions(self, enabled, actor):
        if enabled:
            self.redis.delete(SWITCH_KEY)
        else:
            self.redis.set(SWITCH_KEY, json.dumps(dict(by=actor, at=time.time())))

    def switch_state(self):
        raw = self.redis.get(SWITCH_KEY)
        return dict(enabled=self.executions_enabled(), env_disabled=not executions_enabled(),
                    disabled_by=json.loads(raw) if raw else None)

    # --- santé du runner, mesurée par le worker (seul détenteur des identifiants Google) ---
    def runner_health(self):
        raw = self.redis.get(RUNNER_HEALTH_KEY)
        return json.loads(raw) if raw else None

    def store_runner_health(self, data):
        self.redis.set(RUNNER_HEALTH_KEY, json.dumps(data), ex=7 * 86400)

    # --- limitation des tentatives de connexion ---
    def login_allowed(self, keys, limit=5, window=900):
        return all(int(self.redis.get(LOGIN_ATTEMPTS + key) or 0) < limit for key in keys)

    def login_failed(self, keys, window=900):
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.incr(LOGIN_ATTEMPTS + key)
            pipe.expire(LOGIN_ATTEMPTS + key, window)
        pipe.execute()

    def login_succeeded(self, keys):
        self.redis.delete(*[LOGIN_ATTEMPTS + key for key in keys])
