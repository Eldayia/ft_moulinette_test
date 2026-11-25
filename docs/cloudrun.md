# Exécution distante sur Google Cloud Run — état, constats et plan

Ce document suit la mission décrite dans [AGENT.md](../AGENT.md). Il distingue ce qui est **vérifié dans la documentation officielle**, ce qui est **implémenté et testé localement**, et ce qui **reste à valider sur Google Cloud**. Aucun test local ou mock ne vaut validation de l’isolation Cloud Run.

**Statut au 25 novembre 2026 :** phases 1 et 2 terminées et testées localement (abstraction, protocole, client `CloudRunRunner`, service runner-api avec un double de la CLI `sandbox`) ; phase 3 (images) à faire. Aucune ressource Google Cloud n’a été créée. Aucun accès Google Cloud (ni `gcloud`, ni credentials) n’est disponible dans l’environnement de développement.

## 1. Audit du dépôt

| Élément | Constat |
| --- | --- |
| Moteur | `cli/ft_moulinette`, Python 3.10+, bibliothèque standard uniquement. Point d’entrée `engine.run(target, …, progress=None)`, CLI `ft-moulinette <cible> --json [--progress]`. |
| Projets | Libft 1.3 (43 fonctions) et Printf 1.1 (12 groupes). Pas de sélection de fonctions : dossier complet ou un seul fichier. |
| Rapport | JSON `schema_version: 1`, `module`, `summary`, `results[]` (`file`, `line`, `column`, `check`, `status`, `message`, optionnels `diagnostics`, `raw_message`). Statuts par contrôle : `pass`, `fail`, `missing`, `blocked`, `unavailable`, `skip` (`manual`/`reviewed` hérités). |
| Isolation actuelle | Aucune : le moteur copie le projet dans un dossier temporaire, mais Makefile et binaires s’exécutent avec les droits de l’utilisateur. Délais par commande (15 s par défaut), journaux bornés à 64 Kio par commande. |
| Outils externes | `cc`, `make`, `ar`, `nm`, optionnellement `valgrind`, `norminette` ; injection malloc via `-Wl,--wrap=malloc` (linker GNU). Pas d’ASan/UBSan aujourd’hui. |
| Interfaces d’exécution | CLI ; intégrations Neovim, VSCode, CLion (toutes lancent la CLI locale et lisent `--json`) ; interface web locale `web/` (stdlib, lance la CLI en sous-processus, écoute en boucle locale uniquement). |
| Tests | `unittest`, compilent du vrai C : 46 tests CLI, 33 tests web. |
| Stack VPS de la spécification globale | **Absente du dépôt** : ni SvelteKit, ni FastAPI public, ni PostgreSQL, ni Redis/RQ, ni authentification. `web/` est un outil local, pas la plateforme publique. |
| CI | Aucun workflow GitHub Actions. |

Risques identifiés : exécution de Makefiles et de binaires arbitraires, préprocesseur C (`#include` de fichiers système), archives malveillantes, sorties massives, boucles infinies, consommation mémoire, et falsification du rapport (le code évalué s’exécute dans le même environnement que le moteur, voir §4.4).

## 2. Constats vérifiés dans la documentation officielle

Sources lues le 25 novembre 2026 : [code-execution](https://docs.cloud.google.com/run/docs/code-execution), [services/sandboxes](https://docs.cloud.google.com/run/docs/configuring/services/sandboxes), [sandbox-cli](https://docs.cloud.google.com/run/docs/reference/sandbox-cli), [jobs/sandboxes](https://docs.cloud.google.com/run/docs/configuring/jobs/sandboxes), [service-to-service](https://docs.cloud.google.com/run/docs/authenticating/service-to-service), [tutoriel WIF](https://docs.cloud.google.com/iam/docs/tutorial-cloud-run-workload-id-federation). La page [tarifs](https://cloud.google.com/run/pricing) n’a pas pu être lue automatiquement ; aucun tarif n’est repris de mémoire.

### Activation

- Fonctionnalité **Preview** (conditions Pre-GA). Les exemples YAML portent l’annotation `run.googleapis.com/launch-stage: BETA` et les commandes passent par `gcloud beta`.
- Activation : `gcloud beta run deploy SERVICE --image IMAGE_URL --sandbox-launcher`, ou `sandboxLauncher: true` dans l’entrée du conteneur (`spec.template.spec.containers[]`), appliqué par `gcloud run services replace service.yaml`.
- Environnement d’exécution de deuxième génération imposé.
- Binaire : `/usr/local/gcp/bin/sandbox`, utilisable seulement dans Cloud Run une fois les sandboxes activées.
- Rôles pour déployer : `roles/run.developer` sur le service, `roles/iam.serviceAccountUser` sur l’identité de service.

### CLI `sandbox`

- Commandes documentées : `do`, `run`, `exec`, `fork`, `tar`, `delete`. Aucune commande `list`, `kill`, `stop` ou `cp`.
- `sandbox do [flags] -- <commande> [args…]` : crée la sandbox, exécute, puis la supprime.
- Options utiles de `do` : `--sandbox-name` (identifiant `^[a-zA-Z0-9][a-zA-Z0-9-]*$`, unique), `--rootfs` (répertoire racine, défaut `/`, lecture seule sauf `--write`), `--mount type=bind,src=<abs>,dst=<abs>[,readonly]` (lecture-écriture par défaut, `..` refusé), `-e/--env KEY=VALUE` (pas d’héritage de l’environnement hôte), `-w/--workdir`, `--stdin`/`--stdout`/`--stderr` (défaut `true`), `--write`, `--allow-egress`, `--import-tar`/`--export-tar`/`--sync-tar`.
- `sandbox delete --force <id>` arrête et supprime ; il sort en `1` si l’identifiant n’existe plus.
- **Code de sortie** : `0` si la commande réussit, `1` pour toute erreur de la CLI **ou** tout code non nul de la commande. Le code exact de la commande interne n’est pas transmis.
- **Aucune option documentée** de délai, d’utilisateur, de CPU, de mémoire, de format JSON ou de template.

### Isolation

- Réseau sortant **bloqué par défaut** ; `--allow-egress` l’ouvre vers Internet et les endpoints VPC accessibles depuis l’instance.
- Pas d’accès par défaut au serveur de métadonnées, aux secrets, aux identifiants ni aux variables d’environnement de l’hôte.
- Système de fichiers racine de l’hôte monté en lecture seule ; seul `/tmp` est inscriptible (en mémoire).
- Processus exécutés **en utilisateur non root, avec `sudo`**.
- CPU et mémoire **partagés** avec l’instance ; aucune limite par sandbox, aucun nombre maximal ni délai documentés.
- Non documenté : technologie d’isolation, restrictions d’appels système, ptrace, signaux, pseudo-terminaux, régions disponibles (europe-west1 non confirmée).

### Authentification

- Le jeton est un **ID token** dont l’audience est l’URL du service (ou une audience personnalisée ; les domaines personnalisés ne sont pas acceptés comme `aud`). Il expire environ une heure après sa création.
- En-tête `Authorization: Bearer ID_TOKEN` (ou `X-Serverless-Authorization`).
- Python : `google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)` avec les identifiants par défaut, par exemple une clé de compte de service via `GOOGLE_APPLICATION_CREDENTIALS`.
- Autorisation sur un seul service : `gcloud run services add-iam-policy-binding SERVICE --member='serviceAccount:…' --role='roles/run.invoker'`.
- Workload Identity Federation : pool, fournisseur OIDC, `roles/iam.workloadIdentityUser`, puis génération de l’ID token par emprunt d’identité du compte de service. Les commandes du tutoriel contiennent des coquilles et seront vérifiées avant d’être reprises.

## 3. Écarts avec la mission

| Mission | Constat | Décision |
| --- | --- | --- |
| §8 : sandbox template `c-execution` avec l’image `sandbox-c` | Aucun template ni champ YAML documenté | Pas de champ inventé. Les deux images restent distinctes à la construction ; le système de fichiers de `sandbox-c` est copié dans l’image parente sous `/opt/sandbox-rootfs`, puis passé à `sandbox do --rootfs /opt/sandbox-rootfs`. Les outils C ne sont ni dans le `PATH` ni exécutés par le parent. **À valider sur GCP** : `--rootfs` vers un dossier autre que `/`. |
| §9 : limites par soumission (mémoire, processus, fichiers) | Aucune option CLI ; processus avec `sudo`, donc tout `ulimit` posé dans la sandbox peut être levé par le code soumis | Limites effectives : taille de l’instance (1 vCPU, 2 Gio), concurrence 1 par instance (une seule soumission par instance), délai global imposé par le parent (arrêt puis `sandbox delete --force`), sortie bornée lue par le parent, délais par commande du moteur. **Bloquant pour une ouverture publique**, acceptable pour la bêta privée. |
| §9 : volumes mémoire avec sous-répertoires | Seuls `--mount` en bind et `/tmp` en mémoire sont documentés | Dossier unique par soumission dans le `/tmp` du parent (le système de fichiers de Cloud Run est en mémoire), monté en `readonly` dans la sandbox. Aucun montage en écriture. |
| §15 : ne pas se fier au stdout du programme évalué | Le moteur compile et exécute le code évalué dans la même sandbox que lui ; avec `sudo`, ce code peut agir sur le moteur ou imprimer un faux rapport | Le rapport est validé strictement (schéma, taille, cohérence) avant usage, et son résultat dérivé par du code de confiance côté parent. **Limite documentée** : un étudiant peut falsifier son propre rapport. Cela ne touche ni les autres utilisateurs ni l’infrastructure, mais la plateforme ne doit pas servir de notation officielle. Piste : une sandbox par étape. |
| §10 : liste des fonctions à tester | Le moteur ne sait pas filtrer les fonctions | Champ prévu dans le protocole v1, validé contre la liste connue ; une valeur non vide est refusée avec `unsupported` jusqu’à son support par le moteur. |
| §16 : ASan/UBSan | Absents du moteur | Pas de faux positif : seuls les analyseurs réellement exécutés sont déclarés. |
| Stack VPS (SvelteKit, FastAPI, PostgreSQL, Redis/RQ) | Absente du dépôt | Le dépôt fournit l’abstraction, le client `CloudRunRunner`, la fonction de tâche du worker et sa configuration Compose. La plateforme publique relève de la spécification globale. |

## 4. Architecture retenue

```
cli/              moteur et CLI (inchangés, autonomes, stdlib)
web/              interface web locale (outil personnel, boucle locale)
runners/          ft_moulinette_runners : ExecutionBackend, protocole v1, validation des fichiers,
                  LocalRunner, MockRunner, CloudRunRunner, DockerRunner (développement)
workers/cloudrun/ service runner-api déployé sur Cloud Run (FastAPI) : validation, orchestration sandbox
docker/cloudrun/  Dockerfile.runner, Dockerfile.sandbox
deploy/gcp/       bootstrap.sh, build.sh, deploy.sh, smoke-test.sh, service.yaml.template
docs/             cloudrun.md (ce document), sécurité, coûts, architecture, déploiement Docker
```

### 4.1 Abstraction `ExecutionBackend`

Interface commune : `capabilities()`, `check()` (disponibilité), `submit(Submission) → Execution`, `cancel()` si le backend le permet. Le résultat sépare explicitement le rapport (`report`), la catégorie de résultat (`outcome`), les métadonnées et une erreur typée (`user` ou `infrastructure`). La sélection se fait par configuration explicite. **Aucun repli automatique** : en mode production, un backend non isolé (`local`, `docker`, `mock`) est refusé au démarrage.

### 4.2 Protocole v1 (VPS → runner-api)

`POST /v1/execute`, `multipart/form-data` avec deux parties :

- `metadata` (JSON) : `protocol: 1`, `submission_id` (32 caractères hexadécimaux, sert à la déduplication), `project` (`libft`, `printf`), `functions` (liste, vide pour l’instant), `tests_version`, `options` validées (`norm`, `memory`, `build`, `iterations`, `seed`), `limits` (bornées par le maximum du service).
- `archive` : une archive ZIP. Toutes les méthodes de soumission (fichiers, dossier, code collé, ZIP) sont normalisées en ZIP sur le VPS, puis revalidées par le runner.

Réponse : `protocol`, `submission_id`, `outcome`, `report` (schéma ft-moulinette inchangé), `metadata` (backend, versions, durées, statut de sandbox, motif d’interruption, analyseurs utilisés et indisponibles) et `error` (`category`, `message`). Aucune commande, option de compilation, image, URL ni chemin système n’est acceptée.

### 4.3 Exécution d’une soumission dans le runner

1. Validation de la requête et de l’archive (§12 de la mission) ; extraction sûre dans `/tmp/ftm/<submission_id>/input`.
2. `sandbox do --sandbox-name ftm-<id> --rootfs /opt/sandbox-rootfs --stdin=false --mount type=bind,src=…/input,dst=/submission,readonly --env PATH=… -- python3 /opt/ft-moulinette/bin/ft-moulinette /submission --json --progress …`, sans `--allow-egress` ni `--write`.
3. Le parent lit stdout et stderr de façon bornée, applique le délai global, puis arrête le processus et lance `sandbox delete --force ftm-<id>` en cas de dépassement.
4. Le rapport est validé ; sans rapport valide, le résultat est une erreur d’infrastructure, jamais un succès. Le résultat global est calculé côté parent à partir des contrôles.
5. Nettoyage du dossier dans un bloc `finally`.

### 4.4 Correspondance des résultats

Le résultat global (`outcome`) est dérivé des contrôles par du code de confiance : `success`, `compilation_error`, `norm_error`, `test_failure`, `memory_error`, `timeout`, `resource_limit`, `cancelled`, `infrastructure_error`, `sandbox_unavailable`, `unsupported`. Les statuts par contrôle du schéma existant ne changent pas.

## 5. Plan et avancement

| Phase | Contenu | État |
| --- | --- | --- |
| 1 | Audit, abstraction, protocole, validation des fichiers, `LocalRunner`, `MockRunner`, `CloudRunRunner` (client), tests de non-régression | Fait (65 tests `runners/`, voir §5.1) |
| 2 | Service runner-api (FastAPI), orchestration `sandbox`, rapports, vérification IAM côté client | Fait localement (`workers/cloudrun/`, 14 tests avec double de la CLI sandbox, voir §5.2) |
| 3 | Images Docker, rootfs sandbox, limites, tests de sécurité locaux | À faire |
| 4 | Fonction de tâche RQ, Compose OVH, configuration, quotas | À faire |
| 5 | Scripts GCP, CI GitHub Actions, documentation coûts et sécurité | À faire |
| 6 | Mode distant des intégrations (via l’API OVH), observabilité, interface | À faire (dépend de l’API publique OVH, absente) |
| 7 | Validation réelle sur Google Cloud | Nécessite ton accès GCP et ton autorisation |

### 5.1 Phase 1 : livré

- Paquet `runners/` (`ft_moulinette_runners`, bibliothèque standard) : `base.py` (interface, types, erreurs `user`/`infrastructure`), `limits.py` (limites §12 et §14, lecture `FTM_LIMIT_*`), `workspace.py` (archive déterministe, validation et extraction sûres), `protocol.py` (métadonnées v1, validation stricte des rapports, résultat global, analyseurs), `execution.py` (lancement borné partagé avec le futur runner), `local.py`, `mock.py`, `cloudrun.py` (client, ID token en modes `key` et `wif`), `config.py` (sélection explicite, refus en production, interrupteur).
- Correctif moteur : la copie de travail redevient inscriptible quand la source est en lecture seule ; avant, `make` échouait à tort sur un montage `readonly` (`cli/tests/test_readonly.py`).
- Défauts trouvés et corrigés par les tests : écrasement silencieux de deux noms identiques après normalisation NFC, rapport légitime refusé (champ `message` des diagnostics), liste des fonctions lue avant que le moteur soit importable.
- Les délais du moteur restent par commande : le délai par test individuel (3 s dans la mission) n’est pas distinct de celui de compilation. `command_timeout` couvre les deux.

### 5.2 Phase 2 : livré

- `workers/cloudrun/runner_api/` : `app.py` (FastAPI, endpoints internes, pas de documentation publique, une exécution à la fois, déduplication par instance, interrupteur, échec fermé), `sandbox.py` (commande `sandbox do` limitée aux options documentées, suppression systématique, délai global), `settings.py` (remplacement de la CLI sandbox interdit en production), `logs.py` (JSON structuré, champs autorisés seulement).
- Dépendances figées : `requirements.txt` (exécution), `requirements-dev.txt` (tests).
- L’authentification est assurée par IAM devant le conteneur : le service ne vérifie pas lui-même le jeton et ne doit jamais être déployé avec accès anonyme (contrôlé par `deploy.sh`, phase 5).
- Durées de compilation et de tests : non mesurées séparément par le moteur ; seules la durée totale et la durée de la sandbox sont rapportées (`compile_seconds` et `tests_seconds` valent `null`).

## 6. Vérifications restant à faire sur Google Cloud

Liste tenue à jour à mesure de l’avancement ; elle demande un projet GCP et ton autorisation explicite avant toute ressource facturable.

- Disponibilité des sandboxes en `europe-west1`.
- `sandbox do --rootfs /opt/sandbox-rootfs` fonctionne avec un dossier autre que `/` ; `gcc`, `make`, `valgrind`, `norminette` y fonctionnent ; fork, exec, threads, signaux, pipes.
- Réseau sortant bloqué, serveur de métadonnées inaccessible, aucune variable d’environnement de l’hôte visible.
- Montage `readonly` réellement en lecture seule malgré `sudo`, et lisible par l’utilisateur non root de la sandbox (dossier `0755`, fichiers `0644`).
- Code de sortie et suppression réels : `sandbox do` supprime-t-il la sandbox quand la commande échoue ? `delete --force` renvoie-t-il 1 ensuite ?
- Comportement de `sandbox delete --force` après dépassement du délai, et absence de sandbox orpheline.
- Comportement à la limite mémoire de l’instance (OOM) et classement correct en `resource_limit`.
- Accès anonyme refusé (HTTP 403 sans jeton) et seul `ft-moulinette-invoker` autorisé.
