# Déploiement Google Cloud du service runner-api

Cloud Run sandboxes est une fonctionnalité **Preview** (conditions Pre-GA). Aucune de ces commandes n’a encore été exécutée sur un vrai projet : la première exécution sert de validation, et ses résultats sont à reporter dans `docs/cloudrun.md` §6.

Prérequis : `gcloud` (avec les commandes `beta`) authentifié, Docker, Python 3, un projet GCP **dédié** avec facturation active, et pour ton compte `roles/run.developer` et `roles/iam.serviceAccountUser` sur le compte runtime.

## Procédure

```sh
cp deploy/gcp/config.env.example deploy/gcp/config.env   # renseigner PROJECT_ID (pas de secret)
deploy/gcp/bootstrap.sh       # API, Artifact Registry, comptes de service (avec confirmations)
deploy/gcp/build.sh           # tests, construction et vérification locales, rien n'est publié
deploy/gcp/build.sh --push    # publication et digests dans deploy/gcp/images.env (tag = commit, refus si modifications non commitées)
deploy/gcp/deploy.sh          # déploiement par digest, IAM invoker, vérifications
deploy/gcp/smoke-test.sh      # validation réelle ; code 1 si une vérification essentielle échoue
```

| Script | Ce qu’il fait | Ce qu’il ne fait jamais |
| --- | --- | --- |
| `bootstrap.sh` | Active `run`, `artifactregistry`, `iam`, `iamcredentials` ; crée le dépôt Docker et les comptes `ft-moulinette-runtime` et `ft-moulinette-invoker` s’ils manquent | Créer une clé, accorder un rôle projet, toucher à la facturation |
| `build.sh` | Tests `runners` (et runner-api si `.venv` existe), construction de `sandbox-c`, tests du moteur dans l’image, construction de `runner-api`, vérification de l’échec fermé, publication optionnelle par digest | Publier sans `--push`, publier un arbre non commité |
| `deploy.sh` | Rend `service.yaml.template` (`render.py` refuse les variables manquantes, les valeurs suspectes et les images non figées par digest), `gcloud beta run services replace`, `roles/run.invoker` pour l’invoker seul, échec si `allUsers` ou `allAuthenticatedUsers` apparaissent, vérification de `sandboxLauncher: true`, affichage de l’URL et de la configuration du VPS | `--allow-unauthenticated` |
| `smoke-test.sh` | Accès anonyme refusé, `readyz`, capacités, soumission correcte et soumission en échec, Valgrind et Norminette, sondes (réseau, métadonnées, variables, lecture seule, `sudo`), isolement entre deux soumissions, délai global | Tourner contre un service de production ouvert au public |

`smoke-test.sh` obtient l’ID token avec `gcloud auth print-identity-token --audiences=URL --impersonate-service-account=INVOKER`, ce qui demande `roles/iam.serviceAccountTokenCreator` sur le compte invoker, ou avec `--key-file` (clé JSON). Les options de `gcloud` utilisées par ce script et par la politique de nettoyage n’ont pas été vérifiées en conditions réelles : en cas de refus, consulter `gcloud … --help`.

## Désactiver, retirer, supprimer

| But | Commande |
| --- | --- |
| Suspendre les exécutions | `EXECUTIONS_DISABLED=1` dans `config.env`, puis `deploy.sh` (nouvelle révision, `/readyz` en 503) |
| Couper l’accès du VPS | `gcloud run services remove-iam-policy-binding SERVICE --region REGION --member=serviceAccount:INVOKER --role=roles/run.invoker` |
| Supprimer le service | `gcloud run services delete SERVICE --region REGION --project PROJECT_ID` |
| Supprimer les images | `gcloud artifacts repositories delete REPOSITORY --location REGION --project PROJECT_ID` |
| Supprimer les comptes de service | `gcloud iam service-accounts delete ft-moulinette-invoker@PROJECT_ID.iam.gserviceaccount.com` (idem pour runtime), après révocation de toute clé |
| Tout supprimer | Supprimer le projet dédié |

## Mise à jour des images

Commit, `build.sh --push`, `deploy.sh`, puis `smoke-test.sh`. Chaque déploiement crée une révision immuable référencée par digest. Pour revenir en arrière, remettre l’ancien digest dans `images.env` et relancer `deploy.sh`. La date du snapshot Debian (`DEBIAN_SNAPSHOT`) et les versions figées se changent explicitement, pour appliquer les mises à jour de sécurité.
