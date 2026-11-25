# Sécurité de l’exécution distante (Cloud Run)

Ce document décrit le modèle de menace, les protections en place et leurs limites. Il distingue ce qui est **vérifié localement**, ce qui repose sur la **documentation Google**, et ce qui reste **à valider sur Google Cloud**. Statut au 25 novembre 2026 : aucune validation sur Google Cloud n’a eu lieu, et **l’ouverture au public est bloquée** (voir §5).

## 1. Modèle de menace

Tout contenu soumis est potentiellement hostile : sources C, headers, Makefiles, archives, code collé. Le préprocesseur, `make`, les binaires produits, Norminette et Valgrind interprètent ou exécutent ce contenu.

| Actif à protéger | Menace |
| --- | --- |
| VPS OVH (PostgreSQL, Redis, API, secrets) | Exécution de code, pivot réseau |
| Identité Google (compte runtime, métadonnées) | Vol de jetons, accès aux API Google |
| Autres soumissions | Lecture, altération, persistance entre soumissions |
| Disponibilité et coûts | Boucles infinies, bombes, flots de sortie, multiplication des requêtes |
| Intégrité du rapport | Faux rapport produit par le code évalué |

## 2. Défense en profondeur

| Couche | Protection | Où | État |
| --- | --- | --- | --- |
| VPS (API, worker) | Le VPS ne compile ni n’exécute jamais une soumission. En production, seul `cloudrun` est accepté et aucun repli n’existe (`runners/config.py`). | Code | Testé localement |
| VPS | Validation complète de l’archive avant mise en file : Zip Slip, chemins absolus, liens, fichiers spéciaux, bombes, doublons NFC, chiffrement, extensions, tailles | `workspace.py` | Testé (archives hostiles) |
| VPS → Cloud Run | Service privé IAM, `roles/run.invoker` pour le seul compte invoker, ID token (audience = URL du service), jamais `--allow-unauthenticated` | `deploy.sh`, `cloudrun.py` | Contrôles écrits ; à valider sur GCP |
| runner-api | Revalidation de la requête et de l’archive, protocole versionné, aucune commande, option de compilation, image ni URL acceptée | `app.py`, `protocol.py` | Testé |
| runner-api | Conteneur parent sans outil C dans son `PATH`, utilisateur 10001 ; il n’exécute que la CLI `sandbox` | `Dockerfile.runner` | Vérifié à la construction |
| Sandbox | Sandbox neuve par soumission, réseau sortant bloqué (jamais `--allow-egress`), pas d’accès aux métadonnées ni à l’environnement de l’hôte, racine en lecture seule (pas de `--write`), soumission montée `readonly`, `delete --force` systématique | `sandbox.py` + Google | **Documentation Google ; à valider** |
| Délais | Délai par commande du moteur, délai global imposé par le parent (SIGINT, SIGKILL, puis suppression de la sandbox), délai HTTP Cloud Run | `execution.py` | Testé avec un double ; à valider |
| Sorties | Sortie standard bornée (rapport ≤ 1 Mio), journaux bornés, rapport validé strictement puis résultat recalculé | `execution.py`, `protocol.py` | Testé |
| Ressources | Une soumission par instance (concurrence 1), 1 vCPU et 2 Gio par instance, 2 instances au maximum, quotas applicatifs | Manifeste, `quotas.py` | Testé localement (quotas) |
| Journaux | JSON avec liste de champs autorisés : ni code, ni jeton, ni donnée personnelle ; l’identité de l’étudiant n’est jamais transmise à Cloud Run | `logs.py`, protocole | Testé |
| Interface | Messages affichés via `textContent`, CSP stricte (interface locale) | `web/` | Existant |

## 3. Limites connues (non contournées)

1. **Pas de sandbox template documenté.** Le système de fichiers de `sandbox-c` est copié dans l’image parente et passé à `--rootfs`. Le fonctionnement avec un dossier autre que `/` reste à valider.
2. **Pas de limite de ressources par sandbox.** La documentation n’en propose aucune : CPU et mémoire sont partagés avec l’instance. Le processus évalué dispose de `sudo` (documentation), donc tout `ulimit` posé dans la sandbox peut être levé. Les seules bornes fiables sont la taille de l’instance, la concurrence 1, le délai global du parent et la sortie bornée. Un programme peut épuiser la mémoire de l’instance : l’effet attendu est l’arrêt de l’instance (`resource_limit` ou `infrastructure_error`), à valider.
3. **`sudo` dans la sandbox.** Elle n’empêche pas une élévation locale **à l’intérieur** de la sandbox. L’isolation vis-à-vis de l’hôte, du réseau et des métadonnées repose entièrement sur Google. La résistance du montage `readonly` et de la racine en lecture seule face à `sudo` reste à valider.
4. **Rapport falsifiable par son auteur.** Le moteur et le code évalué partagent la sandbox : un étudiant peut produire un faux rapport **pour sa propre soumission**. Cela ne touche ni les autres utilisateurs ni l’infrastructure (rapport validé, résultat recalculé), mais la plateforme ne doit pas servir de notation officielle. Piste : une sandbox par étape, avec des binaires de test produits hors de portée du code évalué.
5. **Code de sortie ambigu.** `sandbox do` renvoie 1 pour toute erreur. Le verdict ne repose jamais sur ce code : sans rapport valide, le résultat est une erreur d’infrastructure.
6. **Annulation.** Interrompre la requête HTTP ne garantit pas l’arrêt côté Cloud Run. `CloudRunRunner.cancel()` renvoie donc `False`, et le délai interne borne l’exécution.
7. **Fonctionnalité Preview.** Conditions Pre-GA, support limité, comportement susceptible de changer.
8. **`DockerRunner` et `LocalRunner`** ne sont pas des isolations acceptables pour le public : noyau partagé dans un cas, aucune isolation dans l’autre. La configuration les refuse en production.

## 4. Tests de sécurité

| Test | Fichier | Exécuté |
| --- | --- | --- |
| Archives hostiles (Zip Slip, liens, FIFO, périphériques, bombes, doublons, chiffrement, extensions, profondeur) | `runners/tests/test_workspace.py` | Oui, localement |
| Rapports falsifiés ou malformés, résultat incohérent | `runners/tests/test_protocol.py`, `test_local.py` | Oui |
| Délai global, sortie excessive, annulation, plantage du moteur | `runners/tests/test_local.py`, `workers/cloudrun/tests/test_app.py` | Oui (moteur ou sandbox simulés) |
| Échec fermé (pas de sandbox, interrupteur, production) | `workers/cloudrun/tests/test_app.py`, image runner | Oui |
| Sondes réseau, métadonnées, variables, lecture seule (conteneur Docker de développement) | `runners/tests/test_docker.py` | Oui, en local : réseau et métadonnées bloqués, soumission et moteur en lecture seule, aucune variable Google |
| Fork bomb, mémoire, disque, flot de journaux (Docker) | `runners/tests/test_docker.py` (`FTM_ADVERSARIAL_TESTS=docker`) | **Non** : autorisation explicite requise |
| Validation réelle sur Cloud Run : IAM, réseau, métadonnées, variables, lecture seule, isolement entre soumissions, délai, nettoyage | `deploy/gcp/smoke_test.py` | **Non** : nécessite un projet GCP |

Les tests adversariaux ne doivent jamais être lancés sur le VPS de production. Les résultats des tests sur Google Cloud seront consignés dans `docs/cloudrun.md` §6. Avant cela, **l’isolation n’est pas déclarée validée**.

## 5. Conditions d’ouverture

| Étape | Condition |
| --- | --- |
| Bêta privée (5 à 15 utilisateurs connus) | `smoke-test.sh` entièrement vert sur le projet GCP, limites 2 et 3 documentées et acceptées, quotas actifs, alertes budgétaires configurées |
| Ouverture publique | **Bloquée** tant qu’aucune limite de ressources par soumission ne peut être garantie contre un code disposant de `sudo` (limite 2), et tant que l’intégrité des rapports n’est pas nécessaire ou résolue (limite 4) |

## 6. Migration vers une autre isolation

Le contrat `ExecutionBackend` et le protocole v1 ne dépendent pas de Cloud Run. Un autre backend (`CloudRunJobRunner`, VM éphémère, Firecracker, gVisor auto-hébergé) n’a qu’à implémenter `execute()` et `check()` et renvoyer un `ExecutionResult` validé par `protocol.py`. Le service runner-api peut aussi être conservé, en remplaçant seulement `sandbox.py`. Les tests de protocole, d’archives et de rapports restent valables tels quels.
