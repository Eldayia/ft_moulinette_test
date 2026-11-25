# ft-moulinette-runners

Moteurs d’exécution de ft-moulinette derrière une interface commune, `ExecutionBackend`. Le paquet n’utilise que la bibliothèque standard ; seul l’ID token Google de `CloudRunRunner` exige l’extra `cloudrun` (`google-auth`, `requests`, versions figées).

| Moteur | Isolation | Usage |
| --- | --- | --- |
| `LocalRunner` | Aucune | Usage personnel et développement : lance la CLI `cli/` sur la machine courante |
| `MockRunner` | — | Tests et développement d’interfaces ; n’exécute rien |
| `CloudRunRunner` | Sandbox Cloud Run (côté service) | Worker du VPS : appelle le service privé runner-api avec un ID token |
| `DockerRunner` | Insuffisante pour le public | Prévu en phase 3, pas encore disponible |

Le choix se fait par `EXECUTION_BACKEND`. Il n’y a **aucun repli automatique**, et avec `FTM_ENVIRONMENT=production` seul `cloudrun` est accepté. Voir [docs/cloudrun.md](../docs/cloudrun.md) pour l’architecture, le protocole et les limites.

## Contrat

```python
from ft_moulinette_runners.base import Options, Submission
from ft_moulinette_runners.config import backend_from_env
from ft_moulinette_runners.workspace import pack_directory

backend = backend_from_env()                      # ConfigurationError si incomplet
archive, ignored = pack_directory('/chemin/vers/libft')
result = backend.execute(Submission('libft', archive=archive, options=Options(memory=False)))
result.outcome        # success, test_failure, compilation_error, …, infrastructure_error
result.report         # rapport ft-moulinette (schema_version 1), validé, chemins relatifs
result.error          # ExecutionError(category='user' | 'infrastructure', code, message) ou None
```

- `execute()` lève `ExecutionError` (catégorie `user`) si la soumission est refusée avant exécution : archive dangereuse, fichier ciblé absent. Les échecs de tests et les erreurs d’infrastructure figurent dans le résultat.
- Le résultat global `outcome` est toujours recalculé à partir du rapport validé. Un rapport incohérent n’est jamais un succès, et un analyseur indisponible donne `unsupported`.
- `cancel()` ne renvoie `True` que si l’arrêt est confirmé. `CloudRunRunner` renvoie toujours `False` : interrompre la requête HTTP ne garantit pas l’arrêt côté Cloud Run.

## Configuration du worker

| Variable | Rôle |
| --- | --- |
| `EXECUTION_BACKEND` | `cloudrun`, `local`, `mock` (`docker` : phase 3) |
| `FTM_ENVIRONMENT` | `production` : n’accepte que `cloudrun` |
| `CLOUD_RUN_URL` | URL `https://` du service runner-api |
| `CLOUD_RUN_AUDIENCE` | Audience de l’ID token, par défaut `CLOUD_RUN_URL` |
| `GCP_AUTH_MODE` | `key` (défaut, `GOOGLE_APPLICATION_CREDENTIALS`) ou `wif` (Workload Identity Federation) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Mode `key` : chemin du secret Docker `gcp_invoker` ; en mode `wif` : fichier de configuration `external_account` |
| `GCP_INVOKER_SERVICE_ACCOUNT` | Mode `wif` : compte de service emprunté pour produire l’ID token |
| `EXECUTION_TIMEOUT` | Délai global d’une soumission, en secondes |
| `FTM_LIMIT_<NOM>` | Toute limite de `limits.py`, par exemple `FTM_LIMIT_MAX_FILES=100` |
| `FTM_EXECUTIONS_DISABLED` | `1` : interrupteur administrateur, plus aucune exécution |

## Règles de nouvelle tentative de `CloudRunRunner`

| Situation | Nouvelle tentative |
| --- | --- |
| Connexion refusée, nom DNS introuvable | Oui, jusqu’à 3 tentatives : rien n’a été envoyé |
| HTTP 429 (aucune instance disponible) | Oui, jusqu’à 3 tentatives, attente de 1 s puis 4 s |
| HTTP 401 | Une fois, après renouvellement de l’ID token |
| Délai ou coupure après envoi | Non : état inconnu (`unknown_state`) |
| HTTP 403, 500, 503, autre | Non |

## Tests

Depuis `runners/` :

```sh
python3 -m unittest discover -s tests -v
```

65 tests, sans dépendance externe : protocole, validation des archives hostiles (Zip Slip, liens, fichiers spéciaux, bombes, doublons après normalisation, chiffrement), `LocalRunner` avec le vrai moteur et des moteurs factices (délai, sortie excessive, rapport falsifié, annulation), `CloudRunRunner` contre un faux runner-api local (authentification, nouvelles tentatives, état inconnu, réponses falsifiées) et configuration. **Ces tests ne valident pas l’isolation Cloud Run.**
