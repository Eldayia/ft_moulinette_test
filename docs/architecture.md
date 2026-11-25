# Architecture de ft-moulinette

```
                ┌────────────────────────── VPS OVH (Docker Compose) ──────────────────────────┐
 navigateur ──► │ Nginx Proxy Manager ─► ftm-web (SvelteKit) ─► ftm-api (FastAPI, PostgreSQL)    │
 éditeurs   ──► │                           │  valide l'archive, réserve les quotas (Redis)      │
                │                           ▼                                                   │
                │                     Redis / RQ  ◄──── ftm-worker (workers/dispatcher)        │
                │                                        │ CloudRunRunner + ID token (gcp_invoker) │
                └────────────────────────────────────────┼─────────────────────────────────────┘
                                                         │ HTTPS, IAM roles/run.invoker
                ┌──────────────── Google Cloud Run (europe-west1, privé) ──────────────────────┐
                │ runner-api (workers/cloudrun) : revalide, prépare /tmp/ftm/<id>              │
                │    └─► sandbox do --rootfs /opt/sandbox-rootfs --mount …,readonly            │
                │          └─► moteur ft-moulinette (cli/) : make, cc, tests, Norminette,      │
                │              Valgrind, sans réseau ; puis sandbox delete --force             │
                └───────────────────────────────────────────────────────────────────────────────┘
```

## Composants

| Dossier | Rôle | Dépendances |
| --- | --- | --- |
| `cli/` | Moteur et CLI. Seul composant qui compile et teste le code C. Utilisé partout : localement, dans `sandbox-c`, dans les éditeurs. | Bibliothèque standard |
| `web/` | Interface web **locale** (outil personnel, boucle locale), pas la plateforme publique | Bibliothèque standard |
| `runners/` | Contrat `ExecutionBackend`, protocole v1, validation des archives, moteurs `local`, `docker`, `mock`, `cloudrun` | Bibliothèque standard ; `google-auth` pour `cloudrun` |
| `workers/cloudrun/` | Service runner-api sur Cloud Run (FastAPI) : orchestration des sandboxes | FastAPI, uvicorn (figés) |
| `workers/dispatcher/` | Quotas Redis, mise en file RQ, tâche d’exécution distante (réutilisés par la plateforme) | rq, redis, google-auth (figés) |
| `platform/api/` | API publique (FastAPI, PostgreSQL), tâches du worker, administration | FastAPI, SQLAlchemy, psycopg, Alembic (figés) |
| `platform/web/` | Frontend SvelteKit statique | SvelteKit 3, Svelte 5 |
| `docker/cloudrun/` | Images `sandbox-c` (outils C, moteur) et `runner-api` (composants de confiance) | — |
| `docker/ovh/` | Image du worker VPS | — |
| `deploy/gcp/` | Scripts de préparation, construction, déploiement et validation GCP | gcloud, Docker |
| `deploy/ovh/` | Fragment Compose et variables du worker | Docker Compose |

## Principes

- **Un seul moteur.** Les tests ne sont jamais dupliqués : local, Docker et Cloud Run lancent la même CLI avec les mêmes arguments (`runners/execution.py`), et le rapport garde le schéma `schema_version: 1`.
- **Rapport non fiable.** Tout rapport issu d’une exécution est validé (`protocol.validate_report`), puis le résultat global est recalculé (`protocol.classify`) par du code de confiance.
- **Échec fermé, aucun repli.** Sans sandbox, l’exécution est refusée. Un moteur non isolé est refusé en production.
- **Séparation des identités.** Les utilisateurs s’authentifient auprès de l’API OVH. Seul le worker possède une identité Google (`ft-moulinette-invoker`), et Cloud Run ne reçoit jamais l’identité de l’étudiant.
- **Remplaçable.** Changer de technologie d’isolation revient à écrire un nouveau `ExecutionBackend` ou un nouveau `sandbox.py` (voir `docs/cloudrun-security.md` §6).

## Cycle de vie d’une soumission distante

1. L’API valide l’archive (`read_archive`) et réserve les quotas (`RedisQuotas.reserve`, atomique), puis met en file (`enqueue_submission`, `job_id = submission_id`, unique).
2. Le worker exécute `execute_submission` : interrupteur, construction du moteur depuis l’environnement, puis `CloudRunRunner.execute`.
3. `CloudRunRunner` revalide l’archive, obtient l’ID token (en cache) et envoie `POST /v1/execute` en multipart. Il ne relance la requête que si elle n’a certainement pas été transmise ou en cas de 429.
4. runner-api revalide, extrait l’archive dans `/tmp/ftm/<id>/input`, lance `sandbox do` et applique le délai global. Il supprime ensuite la sandbox et l’espace de travail, valide le rapport et répond.
5. Le worker reçoit un `ExecutionResult` validé (`outcome`, `report`, `metadata`, `error`) et libère la réservation de quota. La tâche de la plateforme (`platform/api/ftm_platform/tasks.py`) enregistre le résultat dans PostgreSQL, efface l’archive et met à jour l’étape affichée.

## Correspondance des résultats

| `outcome` | Sens | Catégorie |
| --- | --- | --- |
| `success` | Aucun problème, tous les analyseurs demandés exécutés | Code |
| `compilation_error` | Compilation, liaison ou banc bloqué | Code |
| `test_failure` | Test fonctionnel, présence, Makefile, symboles, prototype, README | Code |
| `memory_error` | Erreur Valgrind | Code |
| `norm_error` | Norminette seule en échec | Code |
| `unsupported` | Analyseur indisponible, option non prise en charge ou soumission refusée par validation | Code ou fonctionnalité |
| `timeout` | Délai global dépassé | Limite |
| `resource_limit` | Sortie excessive, ou limite de l’instance atteinte | Limite |
| `cancelled` | Annulation confirmée (moteurs locaux seulement) | — |
| `infrastructure_error` | Panne, authentification, réponse invalide, état inconnu | Infrastructure |
| `sandbox_unavailable` | Sandbox absente ou désactivée | Infrastructure |
