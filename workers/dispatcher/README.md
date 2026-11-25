# Worker du VPS (Redis/RQ)

Paquet `ftm_dispatcher`, utilisé par la plateforme du VPS (`platform/`) et par son worker RQ. Il ne compile ni n’exécute rien : la tâche délègue au moteur configuré, `cloudrun` en production.

| Module | Rôle |
| --- | --- |
| `quotas.py` | Quotas réservés atomiquement par un script Lua Redis : 20 par utilisateur et par jour, 1 en cours par utilisateur, 20 en file ou en cours au total, 10 s entre deux soumissions, plafond global quotidien de 300. Réservations perdues expirées après 30 min. `MemoryQuotas` applique la même politique en mémoire. |
| `enqueue.py` | `enqueue_submission()` : interrupteur, validation de l’archive, refus des doublons avant réservation, quotas, puis mise en file unique (`job_id = submission_id`, `unique=True` dans RQ 3), sans nouvelle tentative automatique |
| `tasks.py` | `execute_submission()` : tâche RQ. Interrupteur, moteur construit depuis l’environnement (une fois par processus), résultat toujours sérialisable, quota libéré dans tous les cas |

La concurrence d’exécution est le nombre de workers : `rq worker-pool --num-workers $MAX_CONCURRENT_JOBS ftm-submissions` (service `ftm-worker` de `deploy/ovh/docker-compose.platform.yml`, qui exécute les tâches de `platform/api/ftm_platform/tasks.py` en s’appuyant sur ce paquet). Déploiement : [docs/docker-deployment.md](../../docs/docker-deployment.md).

## Tests

```sh
cd workers/dispatcher
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

15 tests. La politique de quotas est vérifiée en mémoire et contre un vrai Redis (image `redis:7.4-alpine` figée par digest, lancée dans Docker, test ignoré sans Docker). S’y ajoutent une mise en file avec exécution par un `SimpleWorker` RQ (moteur `mock`), les doublons, les refus avant réservation, l’interrupteur, la configuration invalide, et le refus de `local` en production.
