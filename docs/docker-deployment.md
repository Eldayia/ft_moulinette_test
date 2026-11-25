# Déploiement de la plateforme sur le VPS OVH

`deploy/ovh/docker-compose.platform.yml` décrit toute la partie VPS :

| Service | Image | Réseaux | Rôle |
| --- | --- | --- | --- |
| `ftm-web` | `docker/ovh/Dockerfile.web` (nginx non privilégié) | `proxy`, `ftm_internal` | Frontend SvelteKit statique, relais `/api` |
| `ftm-api` | `docker/ovh/Dockerfile.platform` | `ftm_internal` | API publique FastAPI : comptes, soumissions, historique, administration |
| `ftm-migrate` | idem | `ftm_internal` | Migrations Alembic, au démarrage, puis s’arrête |
| `ftm-worker` | idem | `ftm_internal`, `ftm_egress` | RQ : délègue chaque exécution à Cloud Run ; **seul** détenteur de l’identité Google |
| `postgres` | `postgres:17-alpine` (figée) | `ftm_internal` | Comptes, sessions, jetons, soumissions, rapports |
| `redis` | `redis:7.4-alpine` (figée) | `ftm_internal` | File RQ, quotas, interrupteur, état du runner |

Aucun service ne compile ni n’exécute de soumission : les images Python et nginx ne contiennent aucun compilateur (vérifié à la construction). Aucun port n’est publié. Nginx Proxy Manager atteint `ftm-web:8080` par le réseau externe `proxy`. `ftm_internal` est un réseau interne, sans accès à Internet.

## Installation

1. Prérequis : runner Cloud Run déployé et validé (`deploy/gcp/deploy.sh`, puis `smoke-test.sh` entièrement vert), Docker Compose, réseau externe `proxy` de Nginx Proxy Manager.
2. Variables : `cp deploy/ovh/platform.env.example deploy/ovh/platform.env`, puis renseigner `FTM_PUBLIC_ORIGIN` (l’URL `https://` publique), `CLOUD_RUN_URL` et `GCP_PROJECT_ID`. Ce fichier ne contient aucun secret ; il est ignoré par Git.
3. Secrets, dans `deploy/ovh/secrets/` (ignoré par Git) :
   ```sh
   install -d -m 700 deploy/ovh/secrets
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > deploy/ovh/secrets/postgres_password
   # clé de l'invoker (mode key) : deploy/gcp/invoker-key.sh create, ou fichier external_account (mode wif)
   sudo chown 10001:10001 deploy/ovh/secrets/*      # utilisateur des conteneurs Python
   sudo chmod 400 deploy/ovh/secrets/*
   ```
   Avec Docker Compose hors Swarm, les secrets fichiers sont montés **avec les droits du fichier hôte** : les options `uid` et `mode` ne s’appliquent pas, d’où le `chown`. PostgreSQL lit son secret en tant que root au démarrage. `gcp_invoker` n’est monté que dans `ftm-worker`.
4. Construction et lancement :
   ```sh
   docker compose -f deploy/ovh/docker-compose.platform.yml --env-file deploy/ovh/platform.env up -d --build
   ```
   Sans le composant `buildx`, construire d’abord les images avec le constructeur classique : `DOCKER_BUILDKIT=0 docker build -f docker/ovh/Dockerfile.platform -t ft-moulinette/platform:local .` et `… Dockerfile.web -t ft-moulinette/web:local .`, puis `up -d --no-build`.
5. Premier administrateur :
   ```sh
   docker compose -f deploy/ovh/docker-compose.platform.yml --env-file deploy/ovh/platform.env \
     exec ftm-api python -m ftm_platform.manage create-user TON_LOGIN --admin
   ```
   Le mot de passe initial est affiché une seule fois. Les autres comptes se créent depuis la page Administration.
6. Nginx Proxy Manager : hôte proxy vers `ftm-web`, port `8080`, certificat TLS, « Block Common Exploits ». Limiter la taille des envois à 12 Mio.

## Exploitation

| Action | Comment |
| --- | --- |
| Suspendre les exécutions | Page Administration, « Suspendre » (effet immédiat, sans redémarrage) ; ou `FTM_EXECUTIONS_DISABLED=1` puis `up -d` |
| Vérifier le runner Cloud Run | Page Administration, « Vérifier maintenant » (exécuté par le worker) |
| Comptes | Page Administration ; ou `manage create-user`, `set-password` (mot de passe sur l’entrée standard), `disable-user` |
| Soumissions bloquées après un arrêt brutal du worker | `manage reap` (marquées en échec, état inconnu, jamais relancées) ; lancé aussi à chaque vérification du runner |
| Rotation de la clé Google (mode key) | `deploy/gcp/invoker-key.sh create` vers un nouveau fichier, remplacer le secret, `up -d ftm-worker`, puis `invoker-key.sh delete ANCIENNE_CLE` |
| Sauvegarde | `pg_dump` du volume `postgres-data` ; les archives soumises sont effacées après exécution, seuls les rapports sont conservés |
| Mise à jour | `git pull`, puis `up -d --build` ; les migrations s’appliquent automatiquement |

## Développement local

`deploy/ovh/docker-compose.local.yml` lance la même pile avec le moteur `mock` (aucune exécution, aucun appel Google), des cookies HTTP, et le frontend sur `http://127.0.0.1:8088`. Utiliser un fichier `deploy/ovh/local.env` avec `FTM_PUBLIC_ORIGIN=http://127.0.0.1:8088` et `CLOUD_RUN_URL=https://non-utilise.invalid`.
