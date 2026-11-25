# Déploiement du worker sur le VPS OVH

Le worker consomme la file Redis/RQ et délègue chaque exécution au service Cloud Run privé. Il ne compile ni n’exécute aucune soumission, et son image ne contient aucun compilateur (vérifié à la construction).

## Prérequis

- Le service runner-api est déployé et validé : `deploy/gcp/deploy.sh`, puis `deploy/gcp/smoke-test.sh` entièrement vert.
- Le déploiement Compose existant (Debian 12, Nginx Proxy Manager, réseau externe `proxy`, Redis sur un réseau interne).

## Étapes

1. Variables : `cp deploy/ovh/worker.env.example deploy/ovh/worker.env`, puis renseigner `CLOUD_RUN_URL` (affichée par `deploy.sh`), `GCP_PROJECT_ID` et `REDIS_URL`. Ce fichier ne contient aucun secret ; il est ignoré par Git.
2. Identité Google du worker, au choix :
   - **Workload Identity Federation** (recommandé) : `GCP_AUTH_MODE=wif`, `GCP_INVOKER_SERVICE_ACCOUNT=ft-moulinette-invoker@PROJET.iam.gserviceaccount.com`, et un fichier de configuration `external_account` (généré par `gcloud iam workload-identity-pools create-cred-config`) comme secret. Le fournisseur d’identité doit délivrer au VPS un jeton OIDC que Google accepte, et le compte invoker doit accorder `roles/iam.workloadIdentityUser` à cette identité externe.
   - **Clé JSON** (bêta privée) : créée **par toi**, jamais automatiquement : `gcloud iam service-accounts keys create … --iam-account=ft-moulinette-invoker@…`. `GCP_AUTH_MODE=key`.
3. Secret : `install -d -m 700 deploy/ovh/secrets`, puis copier le fichier en `deploy/ovh/secrets/gcp_invoker.json` (`chmod 400`). Le dossier est ignoré par Git. Il n’est monté que dans `ftm-worker`, en lecture seule, sous `/run/secrets/gcp_invoker`.
4. Réseaux : `REDIS_NETWORK` désigne le réseau interne de Redis du déploiement existant. Le worker y est rattaché, ainsi qu’à un réseau `egress` pour joindre `*.run.app` et les points d’accès Google. Il n’est **pas** rattaché au réseau `proxy` et ne publie aucun port.
5. Lancement : `docker compose -f docker-compose.yml -f deploy/ovh/docker-compose.worker.yml up -d ftm-worker`.
6. Vérification : `docker compose logs ftm-worker` doit montrer `rq worker-pool` en écoute sur `ftm-submissions`.

## Durcissement du conteneur

Utilisateur 10001, racine en lecture seule, `/tmp` en mémoire (64 Mio, `nosuid,nodev`), `cap_drop: ALL`, `no-new-privileges`, 512 Mio de mémoire et 128 processus au maximum. Le frontend et l’API publique n’ont jamais accès au secret `gcp_invoker`.

## Exploitation

| Action | Commande |
| --- | --- |
| Suspendre les exécutions (maintenance, coûts) | `FTM_EXECUTIONS_DISABLED=1` dans `worker.env`, puis `docker compose up -d ftm-worker` ; ou `rq suspend --url $REDIS_URL` |
| Reprendre | Retirer la variable ; ou `rq resume --url $REDIS_URL` |
| État de la file | `rq info --url $REDIS_URL ftm-submissions` |
| Rotation de la clé (mode key) | Créer une nouvelle clé, remplacer le secret, redémarrer le worker, **puis** supprimer l’ancienne clé dans IAM |
| Mise à jour | `docker compose build ftm-worker && docker compose up -d ftm-worker` |

## Intégration avec l’API publique (hors dépôt)

L’API OVH appelle `ftm_dispatcher.enqueue.enqueue_submission(queue, submission, user_key, quotas)` avec un `user_key` opaque, sans e-mail ni nom. Elle traduit `SubmissionRefused` (quota, maintenance, doublon) et `ExecutionError` (archive refusée) en réponses utilisateur, puis lit le résultat du job RQ (`job.return_value()`). Le format du résultat est celui de `ExecutionResult.to_dict()` ; son champ `report` suit le même schéma que les exécutions locales.
