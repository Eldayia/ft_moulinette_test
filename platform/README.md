# Plateforme web (VPS)

Plateforme communautaire de prévalidation, hébergée sur le VPS OVH. Le code soumis n’y est **jamais** compilé ni exécuté : le worker le confie au runner Cloud Run privé (`workers/cloudrun/`).

| Dossier | Contenu |
| --- | --- |
| `api/ftm_platform/` | API publique FastAPI, modèles PostgreSQL (SQLAlchemy 2, migrations Alembic), tâches du worker RQ, commandes d’administration |
| `web/` | Frontend SvelteKit 3 (Svelte 5), application monopage statique servie par nginx |

Déploiement : [docs/docker-deployment.md](../docs/docker-deployment.md).

## Fonctionnalités

- Comptes créés par un administrateur (bêta privée). Mots de passe `scrypt` (bibliothèque standard), sessions serveur dans un cookie `HttpOnly`, `Secure` et `SameSite=Strict`. Limitation des tentatives de connexion par compte et par adresse.
- Soumission d’une archive ZIP, d’un dossier ou de fichiers (chemins relatifs conservés), ou de code collé. Validation complète sur le VPS, revalidation par le runner. Fichier ciblé optionnel, choix des contrôles.
- Étapes affichées uniquement quand le worker les atteint : en attente (avec position dans la file), préparation, exécution distante, analyse, terminé ou erreur.
- Résultat classé : ton code (compilation, tests, mémoire, norme), limite atteinte, fonctionnalité non prise en charge, erreur Google Cloud ou plateforme. Rapport filtrable, identique au format local.
- Historique personnel. L’archive est effacée après exécution ; seul le rapport est conservé et peut être supprimé.
- Jetons personnels (`ftm_pat_…`) pour la CLI et les éditeurs, révocables. Seule leur empreinte est stockée. Ces outils parlent à cette API, jamais à Google Cloud.
- Administration : interrupteur immédiat des exécutions (bandeau de maintenance), état du runner vérifié par le worker, file et quotas, soumissions par jour, résultats, taux d’échec d’infrastructure, durée moyenne, consommation estimée, gestion des comptes.

## Sécurité

| Sujet | Mesure |
| --- | --- |
| CSRF | Écritures par cookie : en-tête `x-ftm-csrf: 1` obligatoire (impossible à poser depuis un autre site sans CORS) et `Origin` égal à `FTM_PUBLIC_ORIGIN`. Les jetons `Bearer` ne dépendent d’aucun cookie ambiant. |
| XSS | Svelte échappe toute interpolation (aucun `{@html}`). CSP stricte en balise meta : scripts et styles `'self'` plus empreintes générées, un seul attribut `style` autorisé par empreinte (annonceur de navigation de SvelteKit). `frame-ancestors 'none'`, `nosniff` et `no-referrer` envoyés par nginx. |
| Identifiants Google | Absents de l’API et du frontend. Secret `gcp_invoker` monté dans le seul worker ; la page d’administration lit l’état du runner mesuré par le worker. |
| Données | Archives effacées après exécution ; Cloud Run ne reçoit aucune identité d’étudiant ; mot de passe PostgreSQL en secret Docker. |
| Robustesse | Soumission prise atomiquement par le worker (pas de double exécution), quotas réservés avant mise en file et libérés dans tous les cas, soumissions bloquées marquées « état inconnu » sans nouvelle tentative. |

## Développement

```sh
# API (tests contre PostgreSQL et Redis lancés dans Docker)
cd platform/api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v

# Frontend
cd platform/web
npm ci
npm run check && npm run build
npm run dev        # relaie /api vers http://127.0.0.1:8000
```

API en local : `DATABASE_URL=… REDIS_URL=… FTM_ENVIRONMENT=development FTM_PUBLIC_ORIGIN=http://127.0.0.1:5173 FTM_COOKIE_SECURE=0 .venv/bin/uvicorn --factory ftm_platform.app:create_app --port 8000` (avec `PYTHONPATH` incluant `runners/` et `workers/dispatcher/`). Pile complète : `deploy/ovh/docker-compose.local.yml`.
