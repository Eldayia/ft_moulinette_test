# runner-api : service d’exécution Cloud Run

API privée déployée sur Cloud Run, appelée uniquement par le worker du VPS (`CloudRunRunner`). Elle valide la requête, prépare un espace par soumission et lance le moteur ft-moulinette dans une **sandbox Cloud Run neuve**, via la CLI officielle `/usr/local/gcp/bin/sandbox`. Le conteneur parent ne compile ni n’exécute jamais le contenu soumis.

État : implémenté et testé localement avec un **double de la CLI `sandbox`**. Aucune validation sur Google Cloud n’a encore eu lieu (voir [docs/cloudrun.md](../../docs/cloudrun.md), §6).

## Endpoints

| Méthode et chemin | Rôle |
| --- | --- |
| `GET /healthz` | Le processus répond |
| `GET /readyz` | `200 {"ready": true}` si la CLI sandbox, le système de fichiers de la sandbox, le moteur et l’espace de travail sont utilisables et les exécutions activées ; sinon `503` avec `detail` |
| `GET /v1/capabilities` | Protocole, projets, analyseurs, limites, versions d’image et de tests |
| `POST /v1/execute` | Protocole v1 : `multipart/form-data` avec `metadata` (JSON) et `archive` (ZIP) |

Réponses de `/v1/execute` :

| Statut | Signification |
| --- | --- |
| `200` | Résultat v1 (`protocol`, `submission_id`, `outcome`, `report`, `metadata`, `error`), y compris `timeout`, `infrastructure_error` ou `unsupported` |
| `400`, `411`, `413`, `415`, `422` | Requête ou soumission refusée (`error.category = "user"` pour les fichiers) ; aucune sandbox lancée |
| `409` | Même `submission_id` déjà en cours sur cette instance |
| `429` | Instance occupée (une exécution à la fois) ; non traité, nouvelle tentative possible |
| `503` | `sandbox_unavailable` ou `disabled` : échec fermé, rien n’est exécuté |
| `500` | Erreur interne, sans détail dans la réponse |

La déduplication garde en mémoire, par instance, les 64 derniers résultats. Un même `submission_id` reçu à nouveau sur la même instance renvoie le résultat déjà produit (en-tête `X-Ftm-Deduplicated: 1`). Elle ne couvre pas plusieurs instances : la déduplication globale relève du VPS.

## Commande lancée par soumission

```
/usr/local/gcp/bin/sandbox do --sandbox-name ftm-<id> --rootfs /opt/sandbox-rootfs --stdin=false \
  --mount type=bind,src=/tmp/ftm/<id>/input,dst=/submission,readonly --workdir /tmp \
  --env PATH=/usr/local/bin:/usr/bin:/bin --env HOME=/tmp --env TMPDIR=/tmp --env LANG=C.UTF-8 \
  -- /usr/bin/python3 /opt/ft-moulinette/bin/ft-moulinette /submission[/<cible>] --json --progress …
```

Puis, dans tous les cas, `sandbox delete --force ftm-<id>`, et suppression de `/tmp/ftm/<id>`. Ni `--allow-egress`, ni `--write`, ni montage en écriture. Le délai global (`FTM_LIMIT_SUBMISSION_TIMEOUT`) arrête la commande (SIGINT, puis SIGKILL). La sortie standard est bornée (`FTM_LIMIT_MAX_REPORT_BYTES`), puis le rapport est validé et le résultat recalculé.

## Configuration (variables non sensibles)

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `PORT` | `8080` | Port d’écoute, fourni par Cloud Run |
| `FTM_ENVIRONMENT` | `production` | `production` interdit tout remplacement de la CLI sandbox |
| `FTM_SANDBOX_ROOTFS` | `/opt/sandbox-rootfs` | Système de fichiers de l’image `sandbox-c`, passé à `--rootfs` |
| `FTM_SANDBOX_ENGINE` | `/opt/ft-moulinette/bin/ft-moulinette` | Lanceur du moteur, vu depuis la sandbox |
| `FTM_SANDBOX_PYTHON` | `/usr/bin/python3` | Interpréteur, vu depuis la sandbox |
| `FTM_WORKSPACE` | `/tmp/ftm` | Espaces de soumission dans le conteneur parent (système de fichiers en mémoire sur Cloud Run) |
| `FTM_IMAGE_VERSION`, `FTM_TESTS_VERSION` | `unknown` | Repris dans les rapports |
| `FTM_LIMIT_*` | voir `runners/ft_moulinette_runners/limits.py` | Limites de fichiers, de sortie et de délais |
| `FTM_EXECUTIONS_DISABLED` | vide | `1` : interrupteur administrateur |
| `FTM_SANDBOX_BIN` | — | **Tests uniquement**, refusé en production |

## Développement

```sh
cd workers/cloudrun
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Les tests utilisent `tests/fake_sandbox.py`, un **double de test qui n’isole rien**. Il reproduit les options et les codes de sortie documentés, consigne chaque appel pour vérifier les options passées, et exécute le moteur directement sur l’hôte. Ils couvrent les options passées à la sandbox, la suppression de la sandbox et de l’espace de travail, l’échec fermé sans sandbox, l’interrupteur, le délai global, une exécution à la fois, la revalidation des archives hostiles, la déduplication, l’absence de code source dans les journaux, et un aller-retour complet `CloudRunRunner` ↔ runner-api sur HTTP local.
