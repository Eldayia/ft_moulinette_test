
# Mission : Intégrer Google Cloud Run Sandboxes à ft-moulinette

## 1. Contexte

Tu travailles dans le dépôt existant `ft-moulinette`.

Ce projet est destiné à devenir une plateforme communautaire de prévalidation des projets C de l'École 42.

Il doit être accessible depuis :

- Le CLI historique.
- Un plugin Neovim.
- Une extension Visual Studio Code.
- Un plugin JetBrains CLion.
- Une interface web.
- Une API REST.
- Des intégrations CI/CD.

L'objectif de cette mission est de développer un backend d'exécution distant basé sur Google Cloud Run Sandboxes afin de ne jamais exécuter du code C utilisateur non fiable sur le VPS principal.

Cette mission complète la spécification globale de ft-moulinette.

Ne supprime aucune fonctionnalité existante et ne remplace pas les modes d'exécution locaux.

## 2. Infrastructure cible

### VPS principal OVH

- Debian 12.
- 6 vCPU.
- 12 Go de RAM.
- Docker Compose.
- Nginx Proxy Manager.
- Réseau Docker externe `proxy`.

Le VPS héberge :

- Frontend SvelteKit.
- Backend FastAPI.
- PostgreSQL.
- Redis.
- File d'attente RQ.
- Authentification.
- Gestion des soumissions.
- Historique.
- Worker d'orchestration.
- Rapports de tests.

Le VPS principal ne doit jamais compiler ou exécuter les soumissions web non fiables.

### Google Cloud

Google Cloud héberge exclusivement :

- Une API privée d'exécution.
- Un orchestrateur de sandbox.
- Les environnements isolés.
- Les outils de compilation et d'analyse C.

Configuration initiale :

- Région : europe-west1.
- Cloud Run Services.
- Environnement d'exécution Gen 2.
- Cloud Run Sandboxes.
- Artifact Registry.
- IAM.
- Facturation par requête.
- Minimum 0 instance.
- Maximum 2 instances.
- Concurrence de 1 par instance.
- 1 vCPU.
- 2 Gio de RAM.
- Timeout HTTP de 120 secondes.

Ces valeurs doivent être configurables.

## 3. Documentation officielle

Avant d'implémenter cette intégration, consulter les documentations officielles actuelles :

- https://docs.cloud.google.com/run/docs/code-execution
- https://docs.cloud.google.com/run/docs/configuring/services/sandboxes
- https://docs.cloud.google.com/run/docs/reference/sandbox-cli
- https://docs.cloud.google.com/run/docs/configuring/jobs/sandboxes
- https://docs.cloud.google.com/run/docs/authenticating/service-to-service
- https://docs.cloud.google.com/iam/docs/tutorial-cloud-run-workload-id-federation
- https://cloud.google.com/run/pricing

Cloud Run Sandboxes est actuellement une fonctionnalité Preview.

Ne pas inventer des options CLI, des paramètres YAML, des SDK ou des fonctionnalités qui n'existent pas.

Vérifier la disponibilité régionale, les restrictions et les limitations actuelles.

Documenter toute limitation empêchant un déploiement sécurisé.

## 4. Analyse du dépôt

Avant toute modification :

1. Analyser le moteur CLI existant.
2. Identifier les fonctionnalités déjà disponibles.
3. Identifier les interfaces d'exécution.
4. Identifier le format des rapports.
5. Identifier les dépendances.
6. Identifier le système de tests.
7. Identifier la stack web existante si elle a déjà été développée.
8. Identifier les risques de sécurité.
9. Rédiger un plan d'intégration.
10. Ajouter les tests de non-régression nécessaires.

Réutiliser au maximum le code existant.

Ne pas dupliquer les tests entre le CLI et le moteur distant.

Adapter l'architecture proposée au dépôt réel.

## 5. Abstraction des moteurs d'exécution

Créer ou étendre une interface commune `ExecutionBackend`.

Elle doit permettre :

- De soumettre une tâche.
- De sélectionner un projet.
- De sélectionner les tests.
- De transmettre des fichiers.
- De gérer les délais.
- De récupérer les résultats.
- De distinguer les erreurs utilisateur des erreurs infrastructure.
- D'annuler une tâche lorsque le backend le permet.
- De vérifier la disponibilité du backend.

Implémentations envisagées :

- `LocalRunner`
- `DockerRunner`
- `CloudRunRunner`
- `MockRunner`

Prévoir la possibilité d'ajouter ultérieurement :

- `CloudRunJobRunner`
- `RemoteVMRunner`
- `FirecrackerRunner`
- D'autres fournisseurs de sandbox.

Le mode CLI local doit rester autonome.

Le mode Docker de développement ne doit pas être considéré comme une isolation suffisante pour des utilisateurs publics.

Le backend Cloud Run doit être sélectionnable par configuration.

Ne jamais basculer automatiquement vers LocalRunner si Cloud Run est indisponible.

En production web, toute absence de sandbox sécurisée doit empêcher l'exécution.

## 6. Organisation du dépôt

Structure indicative :

    ft-moulinette/
    ├── core/
    │   ├── engine/
    │   ├── projects/
    │   ├── reporters/
    │   └── runners/
    │       ├── base.py
    │       ├── local.py
    │       ├── docker.py
    │       └── cloudrun.py
    ├── api/
    ├── workers/
    │   ├── dispatcher/
    │   └── cloudrun/
    │       ├── app.py
    │       ├── schemas.py
    │       ├── sandbox.py
    │       ├── limits.py
    │       ├── workspace.py
    │       └── reporting.py
    ├── web/
    ├── integrations/
    ├── docker/
    │   └── cloudrun/
    │       ├── Dockerfile.runner
    │       ├── Dockerfile.sandbox
    │       └── requirements.txt
    ├── deploy/
    │   └── gcp/
    │       ├── service.yaml.template
    │       ├── bootstrap.sh
    │       ├── build.sh
    │       ├── deploy.sh
    │       ├── smoke-test.sh
    │       └── README.md
    ├── tests/
    │   ├── unit/
    │   ├── integration/
    │   └── security/
    └── docs/
        ├── cloudrun.md
        ├── cloudrun-security.md
        └── cloudrun-costs.md

Cette organisation est indicative.

Respecter les conventions et la structure existantes.

## 7. Images Docker Google Cloud

Créer deux images distinctes.

### Image runner-api

Fichier :

`docker/cloudrun/Dockerfile.runner`

Contient uniquement les composants de confiance :

- Python.
- FastAPI.
- Serveur HTTP.
- Orchestrateur de sandbox.
- Validation des requêtes.
- Gestion des fichiers temporaires.
- Génération et validation des rapports.
- Gestion des erreurs.
- Gestion des limites.

Le service doit écouter sur :

`0.0.0.0:$PORT`

Le port par défaut est 8080.

Cette image ne doit jamais exécuter directement du code C soumis.

Ne pas installer inutilement GCC, Make ou les outils de compilation dans le conteneur parent.

### Image sandbox-c

Fichier :

`docker/cloudrun/Dockerfile.sandbox`

Contient :

- Distribution Linux minimale compatible.
- GCC.
- Clang.
- Make.
- Binutils.
- Norminette.
- Valgrind.
- Python et dépendances nécessaires au moteur de tests.
- AddressSanitizer si disponible.
- UndefinedBehaviorSanitizer si disponible.
- Outils nécessaires aux tests existants.
- Définitions de tests approuvées et versionnées.

Utiliser des versions explicites et reproductibles.

Préinstaller les dépendances lors de la construction de l'image.

Ne pas télécharger de dépendances pendant une soumission.

Ne jamais inclure de secrets ou de credentials dans cette image.

## 8. Sandbox templates

Utiliser de préférence les sandbox templates Cloud Run pour séparer l'environnement de compilation du conteneur parent.

Configurer un template nommé :

`c-execution`

Le template doit utiliser l'image `sandbox-c`.

Activer explicitement `sandboxLauncher` sur le conteneur Cloud Run parent.

Utiliser le binaire fourni par Google :

`/usr/local/gcp/bin/sandbox`

Le fonctionnement attendu repose sur la CLI officielle, notamment :

- `sandbox do`
- `sandbox run`
- `sandbox exec`

Vérifier la syntaxe exacte des commandes avant utilisation.

Une sandbox neuve doit être créée pour chaque soumission.

Privilégier une exécution éphémère de type `sandbox do` lorsque compatible avec le moteur.

Utiliser une sandbox persistante uniquement pendant la durée d'une soumission si plusieurs étapes nécessitent le même environnement.

Détruire systématiquement cette sandbox à la fin.

Ne jamais réutiliser une sandbox entre utilisateurs.

## 9. Sécurité de la sandbox

Cette section est critique.

Les fichiers suivants sont potentiellement hostiles :

- Sources C.
- Headers.
- Makefiles.
- Archives ZIP.
- Contenu collé dans l'éditeur.
- Dépôts Git importés.

Toutes les opérations susceptibles d'exécuter ou d'interpréter ce contenu doivent être réalisées dans un environnement isolé.

Cela inclut :

- Compilation.
- Préprocesseur C.
- Make.
- Exécution des binaires.
- Scripts soumis.
- Tests.
- Norminette.
- Analyse mémoire.

### Réseau

Interdire le réseau sortant depuis la sandbox.

Ne jamais utiliser `--allow-egress`.

Le code utilisateur ne doit pas pouvoir accéder :

- À Internet.
- Au VPS OVH.
- À PostgreSQL.
- À Redis.
- Aux API internes.
- Au serveur de métadonnées Google Cloud.
- Aux credentials du compte de service.

### Système de fichiers

Ne jamais monter le système de fichiers complet du conteneur parent.

Ne jamais monter :

- Des secrets.
- Des fichiers d'authentification.
- Des clés de service.
- Des fichiers de configuration sensibles.
- Le socket Docker.
- Les dossiers d'autres soumissions.

Utiliser des répertoires temporaires isolés.

Pour les templates, privilégier des volumes mémoire avec sous-répertoires uniques par soumission.

Vérifier que les mécanismes d'échange de fichiers sont compatibles avec les restrictions actuelles de Cloud Run Sandboxes.

Utiliser des montages en lecture seule lorsque possible.

Ne jamais faire confiance aux fichiers produits par la sandbox.

### Ressources

Appliquer des limites configurables sur :

- Le temps de compilation.
- Le temps d'exécution individuel.
- Le temps total de soumission.
- La mémoire.
- Les processus.
- Le nombre de fichiers.
- La taille des fichiers.
- La taille des sorties.
- L'espace de stockage temporaire.
- Le nombre de soumissions concurrentes.

Cloud Run limite les ressources au niveau de l'instance.

Les sandbox templates partagent les ressources CPU et RAM de l'instance.

Ne pas prétendre disposer de limites indépendantes par sandbox si le produit ne les propose pas.

Étudier les mécanismes complémentaires réellement disponibles.

Valider leur fonctionnement par des tests.

### Privilèges

Utiliser le niveau de privilèges minimum disponible.

Ne pas prétendre que la sandbox empêche toute élévation locale si l'environnement fourni par Google permet sudo.

Vérifier que les limites essentielles ne peuvent pas être désactivées par le programme soumis.

En cas d'impossibilité, documenter la limitation et bloquer l'ouverture publique.

### Fail closed

Si la sandbox est indisponible :

- Refuser l'exécution.
- Retourner une erreur infrastructure.
- Journaliser l'incident.
- Ne jamais exécuter directement la soumission.
- Ne jamais désactiver l'isolation pour faire passer un test.

## 10. Protocole de communication

Le VPS doit envoyer les soumissions au service Cloud Run via HTTPS.

Le service Cloud Run doit rester privé au sens IAM : aucune invocation anonyme.

Ne jamais exposer directement le runner aux utilisateurs finaux.

Endpoints internes proposés :

- GET /healthz
- GET /readyz
- GET /v1/capabilities
- POST /v1/execute

Le endpoint `/v1/execute` reçoit :

- Identifiant unique de soumission.
- Identifiant du projet.
- Liste des fonctions à tester si pertinent.
- Version des tests.
- Options validées.
- Fichiers sources.
- Limites autorisées.

Utiliser un protocole versionné.

Privilégier multipart/form-data pour transmettre les fichiers et des métadonnées JSON.

Ne pas accepter :

- Des commandes shell arbitraires.
- Des arguments GCC arbitraires non validés.
- Des chemins système arbitraires.
- Des images Docker choisies par les utilisateurs.
- Des URLs de téléchargement arbitraires.
- Des scripts d'orchestration personnalisés.
- Des plugins de tests non approuvés.

Le service Cloud Run n'a pas besoin de connaître l'identité personnelle de l'étudiant.

Transmettre uniquement les informations nécessaires à l'exécution.

## 11. Authentification Google Cloud

Utiliser IAM pour protéger le service Cloud Run.

Créer deux comptes de service distincts.

### ft-moulinette-runtime

Identité du service Cloud Run.

N'accorder aucune permission projet inutile.

Ne pas lui donner les rôles Owner ou Editor.

Il ne doit pas avoir accès aux données de production du VPS.

### ft-moulinette-invoker

Identité utilisée par le worker sur le VPS.

Accorder uniquement le rôle :

`roles/run.invoker`

Restreindre cette permission au service Cloud Run concerné.

### Authentification depuis OVH

Privilégier Workload Identity Federation lorsqu'une identité externe compatible est disponible.

Prévoir une authentification par clé JSON de compte de service comme alternative pour la bêta privée.

Utiliser la bibliothèque officielle `google-auth`.

Générer un ID token Google valide avec pour audience l'URL du service Cloud Run.

Transmettre le token :

`Authorization: Bearer <ID_TOKEN>`

Ne pas utiliser un simple access token OAuth à la place d'un ID token lorsque Cloud Run exige ce dernier.

Gérer :

- Expiration.
- Renouvellement.
- Mise en cache sécurisée.
- Erreurs d'authentification.

Ne jamais journaliser les tokens.

Ne jamais transmettre la clé Google au frontend ou à la sandbox.

Monter les credentials dans le worker OVH en lecture seule avec les secrets Docker.

Ne jamais créer automatiquement une clé permanente sans autorisation explicite.

## 12. Gestion des fichiers

Prendre en charge toutes les méthodes de soumission existantes :

- Fichiers `.c`.
- Fichiers `.h`.
- Makefile.
- Archive ZIP.
- Dossier complet.
- Plusieurs fichiers.
- Code collé.
- Dépôt Git si déjà implémenté.

Préserver les chemins relatifs.

Valider les entrées sur le VPS et sur le runner.

Prévoir des limites initiales configurables :

- Upload total : 5 Mio.
- Taille décompressée : 20 Mio.
- Maximum 200 fichiers.
- Maximum 2 Mio par fichier.
- Sortie de logs : 256 Kio.
- Rapport JSON : 1 Mio.

Ces limites sont des valeurs de départ à ajuster selon les projets.

Protéger contre :

- Zip Slip.
- Traversée de répertoires.
- Bombes ZIP.
- Archives imbriquées.
- Liens symboliques.
- Liens physiques.
- Fichiers spéciaux.
- Noms dupliqués après normalisation.
- Écrasement de fichiers.
- Extensions inattendues.

Ne jamais extraire des fichiers dans un dossier contenant les composants de confiance.

Ne jamais exécuter un Makefile sur le VPS ou dans le conteneur parent.

## 13. Cycle de vie d'une soumission

Le processus cible est le suivant :

1. L'utilisateur soumet son projet.
2. FastAPI valide les fichiers et les quotas.
3. Une soumission est créée dans PostgreSQL.
4. Une tâche est placée dans Redis/RQ.
5. Le worker récupère la tâche.
6. CloudRunRunner obtient un ID token.
7. Le worker appelle le service Cloud Run.
8. Le service valide la requête.
9. Un espace temporaire unique est créé.
10. Une sandbox éphémère est lancée.
11. Les sources et les tests nécessaires sont transférés.
12. La Norminette est exécutée.
13. Le projet est compilé.
14. Les tests fonctionnels sont exécutés.
15. Les tests mémoire compatibles sont exécutés.
16. Le rapport est récupéré et validé.
17. La sandbox est détruite.
18. Les fichiers temporaires sont supprimés.
19. Le rapport est retourné au VPS.
20. PostgreSQL enregistre le résultat.
21. L'interface web affiche le rapport.

Le nettoyage doit être garanti autant que possible via des blocs finally et des mécanismes de récupération après incident.

## 14. Timeout et annulation

Définir plusieurs niveaux de timeout.

Valeurs initiales :

- Compilation : 15 secondes.
- Test individuel : 3 secondes.
- Analyse mémoire : 15 secondes.
- Soumission globale : 60 secondes.
- Requête Cloud Run : 120 secondes.

Ces valeurs doivent être adaptées aux projets.

Une requête HTTP interrompue ne garantit pas automatiquement l'arrêt du traitement Cloud Run.

Implémenter un mécanisme interne de deadline.

Vérifier la terminaison des processus et de la sandbox.

Ne pas annoncer une annulation effective si elle ne peut pas être confirmée.

Éviter les exécutions orphelines.

## 15. Rapports

Réutiliser le format JSON commun à ft-moulinette.

Ajouter des métadonnées :

- Backend : cloudrun.
- Version du moteur.
- Version des tests.
- Version de l'image d'exécution.
- Durée totale.
- Durée de compilation.
- Durée des tests.
- Statut de la sandbox.
- Motif d'interruption.
- Analyseurs utilisés.
- Analyseurs indisponibles.

Distinguer les statuts :

- success
- compilation_error
- norm_error
- test_failure
- memory_error
- timeout
- resource_limit
- cancelled
- infrastructure_error
- sandbox_unavailable
- unsupported

Adapter ces statuts au schéma existant.

Les résultats produits par un programme soumis ne doivent jamais être considérés automatiquement comme fiables.

Les tests de confiance et les résultats attendus doivent être protégés contre les modifications par le programme évalué.

Ne pas déterminer la réussite uniquement à partir d'un message stdout ou d'un code de sortie contrôlé par l'utilisateur.

Valider la structure et la taille du rapport avant enregistrement.

Échapper les sorties dans l'interface web.

## 16. Compatibilité des outils C

Vérifier réellement le fonctionnement dans Cloud Run Sandboxes de :

- GCC.
- Clang.
- Make.
- Norminette.
- Valgrind.
- ASan.
- UBSan.
- Signaux POSIX.
- Pipes.
- Fork.
- Exec.
- Threads.
- Ptrace si nécessaire.
- Tests utilisant des pseudo-terminaux.

Certains projets 42 nécessitent des fonctionnalités système spécifiques.

Ne pas supposer qu'elles sont disponibles dans un environnement sandboxé.

Si Valgrind ne fonctionne pas :

- Étudier ASan et UBSan.
- Documenter les différences.
- Indiquer quel analyseur a été utilisé.
- Marquer les tests incompatibles comme non exécutés.
- Ne jamais produire de faux résultat positif.

Conserver une matrice de compatibilité par backend et par projet.

Ne pas affaiblir l'isolation pour rendre un outil compatible.

## 17. Configuration Docker Compose OVH

Adapter le déploiement existant.

Ajouter au worker uniquement les variables nécessaires :

    EXECUTION_BACKEND=cloudrun
    GCP_PROJECT_ID=
    GCP_REGION=europe-west1
    CLOUD_RUN_URL=
    GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp_invoker
    EXECUTION_TIMEOUT=60
    MAX_CONCURRENT_JOBS=2

Utiliser un secret Docker nommé :

`gcp_invoker`

Le secret doit être accessible uniquement au worker concerné.

Le frontend et l'API publique ne doivent pas accéder directement aux credentials Google.

Préserver :

- Le réseau externe proxy.
- Le réseau interne de PostgreSQL.
- Le réseau interne de Redis.
- La compatibilité Nginx Proxy Manager.

Aucun nouveau port public ne doit être nécessaire sur le VPS pour le runner.

Fournir un `.env.example` sans secret.

## 18. Scripts de déploiement GCP

Créer les fichiers suivants.

### bootstrap.sh

Doit permettre de :

- Vérifier les prérequis.
- Configurer le projet.
- Configurer la région.
- Activer les API Google nécessaires.
- Créer Artifact Registry.
- Créer les comptes de service.
- Préparer les permissions minimales.

Le script doit être idempotent autant que possible.

Ne pas créer automatiquement de clés permanentes.

Ne pas activer de facturation ou de ressources coûteuses sans autorisation.

### build.sh

Doit permettre de :

- Construire runner-api.
- Construire sandbox-c.
- Exécuter les tests disponibles.
- Taguer les images.
- Publier les images sur Artifact Registry.
- Récupérer les digests.

Privilégier les digests d'images pour les déploiements reproductibles.

### service.yaml.template

Doit configurer :

- Cloud Run Service.
- Environnement Gen 2.
- Sandbox launcher.
- Sandbox template c-execution.
- Image runner-api.
- Image sandbox-c.
- Volumes temporaires nécessaires.
- Sous-répertoires isolés.
- Identité runtime.
- CPU.
- RAM.
- Concurrence.
- Autoscaling.
- Timeout.
- Variables d'environnement non sensibles.

Utiliser la syntaxe officielle actuelle.

Ne pas inventer de champs YAML.

Inclure les annotations Preview/Beta requises.

### deploy.sh

Doit permettre de :

- Générer le manifeste.
- Vérifier les variables.
- Déployer le service.
- Configurer IAM.
- Vérifier l'absence d'accès anonyme.
- Vérifier l'activation des sandboxes.
- Afficher l'URL du service.
- Afficher les étapes de configuration du VPS.

Ne jamais activer automatiquement `--allow-unauthenticated`.

### smoke-test.sh

Doit permettre de :

- Vérifier le service.
- Vérifier IAM.
- Vérifier le sandbox launcher.
- Exécuter une soumission C minimale.
- Vérifier la compilation.
- Vérifier le résultat.
- Vérifier l'isolation réseau.
- Vérifier l'absence d'accès aux credentials.
- Vérifier le nettoyage.

Le script doit retourner un code d'erreur si une vérification essentielle échoue.

## 19. Gestion des coûts

L'objectif initial est une bêta privée de 5 à 15 utilisateurs.

Configuration recommandée :

- 0 instance minimum.
- 2 instances maximum.
- 1 requête simultanée par instance.
- 1 vCPU.
- 2 Gio de RAM.
- Facturation par requête.
- Timeout strict.

Mettre en place des quotas côté application :

- 20 soumissions par utilisateur et par jour.
- 1 soumission simultanée par utilisateur.
- 2 soumissions simultanées globalement.
- File d'attente bornée.
- Limitation des tentatives répétées.
- Limitation du volume de logs.

Rendre ces valeurs configurables.

Prévoir un interrupteur administrateur permettant de désactiver immédiatement les exécutions distantes.

Prévoir un plafond applicatif global configurable.

Ne pas présenter les plafonds applicatifs ou les alertes budgétaires Google comme une garantie absolue contre les frais.

Documenter les coûts potentiels :

- Cloud Run.
- Artifact Registry.
- Cloud Build.
- Cloud Logging.
- Transfert réseau.
- Stockage éventuel.

Prévoir une politique de nettoyage des anciennes images Docker.

Créer une documentation pour les alertes budgétaires.

## 20. Gestion des erreurs et résilience

Gérer proprement :

- HTTP 401.
- HTTP 403.
- HTTP 429.
- HTTP 500.
- HTTP 503.
- Timeout réseau.
- Démarrage à froid.
- Sandbox indisponible.
- Quota Google dépassé.
- Mémoire insuffisante.
- Rapport invalide.
- Interruption de connexion.

Utiliser des identifiants de soumission uniques.

Prévoir une stratégie de déduplication.

Ne pas promettre une exécution exactement une fois si l'infrastructure ne le garantit pas.

Limiter les retries.

Ne pas relancer automatiquement une soumission si son état réel est inconnu sans mécanisme de déduplication approprié.

Ne jamais rediriger une soumission distante vers le VPS pour contourner une erreur.

## 21. Tests de sécurité

Ajouter des tests contrôlés permettant de vérifier :

- Boucle infinie.
- Consommation excessive de mémoire.
- Création excessive de processus.
- Production excessive de logs.
- Création excessive de fichiers.
- Lecture de fichiers non autorisés.
- Accès réseau.
- Accès au serveur de métadonnées.
- Accès aux credentials.
- Makefile contenant des opérations non autorisées.
- Archives malformées.
- Traversée de répertoires.
- Liens symboliques.
- Tentative d'altération des résultats.
- Tentative de lecture d'une autre soumission.
- Interruption brutale.
- Nettoyage après timeout.

Réaliser les tests adversariaux uniquement dans un environnement de validation explicitement autorisé et isolé.

Ne jamais les lancer sur le VPS de production.

Ne pas produire de test destructeur non borné.

Documenter les résultats réels.

Ne pas déclarer l'isolation validée si les tests n'ont pas été exécutés sur Google Cloud.

## 22. Observabilité

Ajouter des logs structurés contenant :

- Identifiant de soumission.
- Backend.
- Durée.
- Statut.
- Version des tests.
- Version de l'image.
- Catégorie d'erreur.

Ne jamais journaliser :

- Le code source complet.
- Les credentials.
- Les ID tokens.
- Les données personnelles inutiles.

Prévoir des métriques :

- Soumissions par jour.
- Durée moyenne.
- Jobs en attente.
- Taux d'échec.
- Timeouts.
- Erreurs d'infrastructure.
- Sandbox indisponible.
- Consommation estimée.

Éviter un volume excessif de Cloud Logging.

## 23. Interface web

Adapter l'interface web pour afficher :

- En attente.
- Préparation.
- Exécution distante.
- Analyse des résultats.
- Terminé.
- Erreur infrastructure.

Ne pas inventer de progression détaillée si le runner ne transmet pas réellement cette information.

Afficher clairement la différence entre :

- Un test échoué.
- Une compilation échouée.
- Une erreur de Google Cloud.
- Une fonctionnalité non supportée.
- Une limite de ressources atteinte.

Ajouter une section administrative permettant de consulter :

- État du runner.
- File d'attente.
- Quotas.
- Nombre de soumissions.
- Disponibilité du backend.
- Consommation estimée.

Prévoir l'affichage d'un message de maintenance si les exécutions sont désactivées.

## 24. Intégrations CLI et IDE

Préserver les exécutions locales.

Ajouter un mode distant optionnel dans :

- Le CLI.
- Neovim.
- VS Code.
- CLion.

Les intégrations doivent communiquer avec l'API ft-moulinette hébergée sur OVH, jamais directement avec Google Cloud Run.

Elles ne doivent jamais posséder les credentials Google Cloud.

L'authentification des utilisateurs doit être distincte de l'authentification machine-à-machine.

Les résultats doivent utiliser le même format que les exécutions locales.

Aucun utilisateur ne doit être obligé de créer un compte Google Cloud.

## 25. CI/CD

Adapter GitHub Actions pour :

- Tester CloudRunRunner avec des mocks.
- Tester les schémas API.
- Tester la validation des fichiers.
- Tester la gestion des erreurs.
- Construire les images Docker.
- Analyser les dépendances.
- Analyser les images.
- Valider les manifests.
- Exécuter les tests de non-régression.

Prévoir un workflow de déploiement Google Cloud manuel.

Privilégier GitHub OIDC et Workload Identity Federation pour le CI/CD.

Ne pas stocker de clé JSON Google Cloud dans le dépôt.

Ne pas déployer automatiquement en production après chaque commit.

## 26. Documentation

Créer ou compléter :

- docs/cloudrun.md
- docs/cloudrun-security.md
- docs/cloudrun-costs.md
- docs/architecture.md
- docs/docker-deployment.md

Expliquer :

- La création du projet Google Cloud.
- L'activation des API.
- Artifact Registry.
- IAM.
- Les sandbox templates.
- L'authentification depuis OVH.
- Le déploiement.
- Les variables d'environnement.
- Le fonctionnement du moteur.
- Les limites de compatibilité.
- Les coûts.
- Les quotas.
- La surveillance.
- La mise à jour des images.
- La rotation des clés si utilisées.
- La désactivation du service.
- La suppression des ressources.
- Le dépannage.

Documenter clairement le statut Preview de Cloud Run Sandboxes.

Prévoir une procédure de migration vers une autre technologie d'isolation si nécessaire.

## 27. Critères d'acceptation

La mission est terminée uniquement si :

- Le CLI historique reste fonctionnel.
- Les interfaces locales restent autonomes.
- CloudRunRunner est implémenté.
- Le protocole distant est versionné.
- Les deux Dockerfiles existent.
- Les images peuvent être construites.
- Le manifeste Cloud Run est fourni.
- Le sandbox template est configuré.
- Le service exige une authentification IAM.
- Le worker utilise un ID token valide.
- Les soumissions ne sont jamais exécutées sur OVH.
- Le code non fiable est isolé dans une sandbox.
- Le réseau de la sandbox est bloqué.
- Les fichiers sont isolés par soumission.
- Les limites de ressources sont appliquées.
- Les timeouts sont gérés.
- Les rapports sont cohérents.
- Les erreurs infrastructure sont distinguées.
- Les quotas sont configurables.
- Les scripts de déploiement existent.
- La documentation est complète.
- Les tests locaux et mocks passent.
- Les validations Google Cloud sont documentées.

Si l'accès à Google Cloud n'est pas disponible pendant le développement, implémenter et tester tout ce qui est possible localement.

Fournir ensuite une liste précise des commandes et vérifications restant à effectuer sur GCP.

Ne jamais présenter un test mock comme une validation réelle de l'isolation Cloud Run.

## 28. Ordre d'implémentation

Phase 1 :
- Audit du dépôt.
- Abstraction ExecutionBackend.
- Tests de non-régression.
- CloudRunRunner.

Phase 2 :
- API distante.
- Protocole de soumission.
- Validation des fichiers.
- Rapports.
- Authentification IAM.

Phase 3 :
- Images Docker.
- Sandbox templates.
- Isolation.
- Limites.
- Tests de sécurité.

Phase 4 :
- Intégration Redis/RQ.
- Docker Compose OVH.
- Configuration.
- Gestion des erreurs.

Phase 5 :
- Scripts Google Cloud.
- Déploiement reproductible.
- CI/CD.
- Documentation.

Phase 6 :
- Interface web.
- CLI distant.
- Intégrations IDE.
- Observabilité.

Phase 7 :
- Validation réelle sur Google Cloud.
- Mesures de performance.
- Mesures de consommation.
- Audit de sécurité.
- Préparation de la bêta privée.

## 29. Instructions finales

Commencer immédiatement par analyser le dépôt réel.

Ne pas se limiter à proposer une architecture.

Implémenter les composants nécessaires de manière incrémentale.

À chaque étape :

- Écrire du code réel.
- Ajouter des tests.
- Exécuter les vérifications disponibles.
- Corriger les erreurs.
- Mettre à jour la documentation.
- Préserver les fonctionnalités existantes.
- Utiliser des Conventional Commits lorsque possible.

Ne créer aucune ressource Google Cloud facturable sans autorisation explicite.

Ne pas demander de credentials dans les fichiers du dépôt.

Ne jamais contourner une restriction de sécurité pour rendre un test fonctionnel.

L'objectif est de disposer d'un moteur d'exécution C distant, sécurisé, économique, remplaçable et compatible avec toutes les interfaces de ft-moulinette.
