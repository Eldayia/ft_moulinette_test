# Guide des agents de code — ft-moulinette

Ce document décrit le fonctionnement, les conventions et l’état du dépôt pour permettre à un autre agent de reprendre le travail. Il doit être lu avec [cli/README.md](cli/README.md), qui reste le guide d’installation et d’utilisation de l’outil en ligne de commande.

**État relevé le 25 novembre 2026.** Les constats ci-dessous proviennent du code et des vérifications locales ; les pistes de travail ne sont pas des fonctionnalités déjà livrées.

Le nom `AGENT.md` est volontaire. Il ne faut pas supposer que les outils qui découvrent automatiquement `AGENTS.md` chargeront ce fichier : le référencer explicitement dans leur contexte si nécessaire.

## 1. Mission et périmètre

Le projet fournit un outil local de contrôle pour les sujets 42 **Libft 1.3** et **Printf 1.1**. Le paquet Python est en version **0.3.0**, nécessite Python **3.10+** et n’a pas de dépendance tierce à l’exécution.

L’outil doit aider à comprendre les erreurs grâce à des diagnostics en français, des emplacements exploitables par les éditeurs et des tests reproductibles. Il ne doit pas présenter une réussite automatique comme une certification officielle.

Le fonctionnement vise Linux, avec des outils compatibles GNU. La norme 4.1 est la référence documentaire ; le contrôle réel utilise la version de Norminette accessible dans l’environnement.

## 2. Consignes pour intervenir

1. Lire les fichiers concernés et leurs tests avant de modifier le comportement. Vérifier les instructions locales applicables et l’état des changements existants lorsque les métadonnées Git sont disponibles.
2. Garder les modifications dans le périmètre demandé. Préserver les modifications de l’utilisateur ; ne pas régénérer les archives ou plugins sans raison liée à la tâche.
3. Utiliser la bibliothèque standard Python tant qu’une nouvelle dépendance n’est pas justifiée. Conserver Python 3.10 comme version minimale.
4. Respecter les contrats du sujet encodé ici. Ne pas remplacer les attentes par celles d’un ancien sujet Libft ou de la libc sans vérifier les différences.
5. Pour une correction fonctionnelle, ajouter ou adapter un test qui démontre le comportement attendu et rejette une implémentation incorrecte. Éviter les tests qui recopient uniquement l’implémentation.
6. Passer les commandes externes sous forme de listes d’arguments. Conserver les délais, la gestion des crashes et la terminaison des processus ; ne pas introduire d’interpolation de shell pour les chemins fournis par l’utilisateur.
7. Préserver les chemins originaux dans les diagnostics. Les fichiers temporaires des bancs ne doivent pas être présentés comme des erreurs du projet étudiant.
8. Ne pas traiter un contrôle désactivé ou indisponible comme une réussite. Préserver la distinction entre `skip`, `unavailable`, `blocked` et `fail`.
9. Documenter les nouveaux comportements publics dans le README concerné (`cli/README.md` ou `web/README.md`) et mettre à jour ici les limites ou résultats de validation qui changent.
10. En fin de tâche, indiquer les fichiers modifiés, les vérifications effectuées, leurs résultats et les limites restantes. Ne pas annoncer une suite entièrement verte si des tests échouent ou sont ignorés.

Les projets C et leurs Makefiles exécutent du code avec les droits de l’utilisateur. Les copies temporaires préservent les liens symboliques : ce mécanisme n’est pas un confinement. Utiliser des fixtures temporaires et de confiance pour les tests de développement.

## 3. Carte du dépôt

Le dépôt est organisé en deux parties :

- `cli/` : l’outil existant (moteur Python, lanceur, tests, scripts d’installation et d’archive, intégrations éditeur). Toutes ses commandes se lancent **depuis `cli/`** ; ses scripts résolvent leurs chemins par rapport à leur propre emplacement et l’archive de `package.sh` reproduit le contenu de `cli/` à sa racine.
- `web/` : la partie web, en cours de mise en place (voir section 6).

À la racine : `README.md` (présentation et renvois), ce guide, `CLAUDE.md` et `.gitignore` commun.

Les chemins du tableau suivant sont relatifs à `cli/`.

| Chemin | Responsabilité |
| --- | --- |
| `pyproject.toml` | Métadonnées, version Python, backend setuptools et commande `ft-moulinette` |
| `bin/ft-moulinette` | Lanceur utilisable depuis le dépôt, indépendamment du dossier courant |
| `ft_moulinette/__main__.py` | Arguments CLI, sélection du moteur, JSON et code de sortie |
| `ft_moulinette/engine.py` | Détection du sujet, exécution bornée des processus et orchestration Libft |
| `ft_moulinette/cases.py` | Liste des 43 fonctions, prélude C, assertions et injection malloc Libft |
| `ft_moulinette/prototypes.py` | Signatures publiques Libft attendues |
| `ft_moulinette/runner.py` | Construction/exécution d’un banc Libft, Valgrind et pannes malloc |
| `ft_moulinette/printf.py` | Racine Printf, découverte récursive, compilation et orchestration des groupes |
| `ft_moulinette/printf_cases.py` | Douze groupes et banc C de comparaison avec `snprintf` |
| `ft_moulinette/build.py` | Règles Makefile, état des fichiers et reconstructions après modification |
| `ft_moulinette/audit.py` | Interception via PATH des outils de compilation et d’archivage |
| `ft_moulinette/diagnostics.py` | Extraction des lignes/colonnes et remappage des chemins temporaires |
| `ft_moulinette/explain.py` | Reformulation pédagogique des échecs Libft |
| `ft_moulinette/report.py` | Rapport texte compact et mode détaillé |
| `install.sh` | Installation locale et bloc d’alias Bash/Zsh |
| `package.sh` | Archive de distribution dans `dist/` |
| `integrations/neovim/` | Module Lua, commandes projet/fichier et quickfix |
| `integrations/vscode/` | Extension JavaScript, diagnostics, Output et empaquetage VSIX local |
| `integrations/clion/` | Plugin Java, build local avec SDK installé, alternative Gradle et guide dédié |
| `tests/` | Tests unittest, références C, mutations et fixtures temporaires |

Les dossiers `dist/`, `build/`, `.venv/`, `node_modules/`, les caches Python, les VSIX et les journaux sont ignorés par Git. Un binaire ou une archive présent localement peut être antérieur aux sources.

## 4. Parcours d’exécution et invariants

### Entrée et résultats

`main()` analyse les arguments et appelle `engine.run()`. `detect_project()` respecte `--project`, sinon recherche des marqueurs Printf ; Libft sert de choix par défaut.

Les valeurs publiques par défaut sont : cible `.`, projet `auto`, 500 itérations, graine 42 et timeout 15 secondes. Les itérations et le timeout doivent être strictement positifs. Les graines sont normalisées sur 32 bits dans les bancs. Le timeout s’applique à chaque commande, pas au contrôle global ; les bancs exécutés sous Valgrind disposent d’au moins 30 secondes.

Chaque résultat possède `file`, `line`, `column`, `check`, `status`, `message`. `diagnostics` et `raw_message` sont optionnels. Le JSON expose `schema_version=1`, `module`, `summary`, `results`.

- `module` vaut `libft-1.3` ou `printf-1.1`.
- `summary` ne contient que les statuts présents.
- Les chemins des résultats et diagnostics doivent désigner les fichiers originaux.
- Le préfixe `archive:` identifie les tests contre l’archive produite par le Makefile.
- Les intégrations VSCode et Neovim consomment ce JSON ; ne pas en changer la structure sans examiner ces consommateurs et les tests.
- Sortie 1 si un résultat vaut `fail`, `missing`, `blocked` ou `unavailable` ; 0 sinon ; les erreurs d’arguments et certaines erreurs d’accès sont remontées par argparse avec le code 2.

L’option masquée `--reviewed readme|project|all` et les statuts `manual`/`reviewed` subsistent pour compatibilité. Le moteur courant ne génère pas de rappels de relecture systématiques. Ne pas présenter cette option comme une validation de conformité ni comme une déclaration persistante.

### Libft

Les sources sont découvertes à la racine, avec la convention `ft_<fonction>.c`. Toutes les sources racine disponibles sont compilées pour fournir les dépendances, puis chaque fonction sélectionnée est testée séparément.

En mode fichier, seuls les contrôles de la source sélectionnée sont rapportés pour la compilation et les symboles ; les dépendances restent compilées. En mode header, aucun banc fonctionnel de fonction n’est sélectionné. Les contrôles de projet et de Makefile nécessitent une cible dossier.

Invariants du sujet encodé :

- 43 fonctions obligatoires, listes incluses ; pas de traitement des listes comme bonus facultatifs.
- `ft_lstsize` retourne `unsigned int`.
- Les classifications `isalpha`, `isdigit`, `isalnum`, `isascii`, `isprint` retournent exactement 0 ou 1 ; les oracles doivent normaliser la libc lorsque nécessaire.
- `FUNCTIONS`, `CASES` et `PROTOTYPES` doivent rester cohérents.
- Les auxiliaires définis dans les fichiers des fonctions contrôlées sont attendus `static` ; les variables globales, y compris `static`, sont rejetées par l’analyse des symboles.
- Les échecs malloc utilisent `-Wl,--wrap=malloc`. `--no-memory` désactive Valgrind, mais conserve ces scénarios d’allocation.

Les objets compilés indépendamment et la véritable `libft.a` font l’objet de parcours de tests distincts. Ne pas substituer les objets individuels à l’archive pour masquer un Makefile défectueux.

### Printf

`project_root()` remonte au Makefile parent le plus proche pour une cible fichier. Toutes les sources C non cachées de l’arborescence sont prises en compte ; les dossiers de headers sont ajoutés aux chemins d’inclusion.

Même en mode fichier, le module teste l’ensemble de `ft_printf` ; seule la portée de Norminette est réduite à la cible. Les contrôles de présence, README et Makefile nécessitent une cible dossier.

La sortie est binaire : préserver les NUL de `%c` et la comparaison du nombre d’octets retourné. Les douze groupes s’exécutent séparément : une erreur doit arrêter son groupe, tout en laissant les autres s’exécuter. Les appels internes définis dans le projet sont admis ; ne pas transposer l’interdiction des auxiliaires non `static` de Libft à Printf.

Les formats invalides, bonus, flags/largeurs/précisions, format NULL, `%s` NULL, erreurs d’écriture et pannes malloc restent hors du périmètre courant.

### Processus et Makefile

`engine.execute()` utilise une session de processus dédiée, tue le groupe après timeout et borne la lecture des journaux à 65 536 octets. Les crashes et timeouts doivent produire des diagnostics compréhensibles.

`check_build()` contrôle les règles et leurs effets réels sur les objets et l’archive. `check_rebuilds()` modifie les dates des sources/headers de la copie pour demander une reconstruction. L’absence de relink se mesure aussi par les dates des objets et archives.

`audit_build()` intercepte `cc`, `gcc`, `clang`, `ar`, `libtool` via des lanceurs dans le PATH. Il exige `cc` et les trois flags, observe l’utilisation de `ar`, rejette `libtool` et, pour Libft, `-std=c99`. Les commandes par chemins absolus peuvent échapper à l’observation : conserver le signalement `unavailable`.

## 5. Installation, intégrations et livraison

`install.sh` vérifie Python et `cc`, `make`, `ar`, `nm`. Il installe `cli/ft_moulinette/` et `cli/bin/` dans `~/.local/share/ft-moulinette`, ainsi que `cli/README.md`, le script d’installation et `pyproject.toml`. Le lanceur externe utilise le Python ayant exécuté l’installation.

Préserver le comportement sans réseau, la gestion des chemins contenant espaces/apostrophes, le respect de `$ZDOTDIR`, la conservation des configurations shell existantes et l’idempotence du bloc d’alias. L’installateur ne copie ni les tests ni les intégrations.

`package.sh` crée `cli/dist/ft-moulinette.tar.gz` avec les intégrations, mais sans les tests, ce guide, ni la partie web. Il peut inclure les builds d’intégrations déjà présents : inspecter leur fraîcheur avant une livraison. Ne pas supposer qu’une archive existante est à jour.

Commandes de fabrication, depuis `cli/` et uniquement si la tâche le nécessite :

```sh
sh package.sh
python3 integrations/vscode/package_local.py
python3 integrations/clion/build_local.py --clion /opt/clion
```

Les versions des composants ne sont actuellement pas alignées : paquet Python 0.3.0, extension VSCode 0.1.0, version Gradle CLion 0.2.0, ZIP CLion local 0.3.0. Le build CLion local utilise le SDK installé ; Gradle référence CLion 2025.3 et Java 21. Ne pas annoncer une version unique des intégrations sans mettre à jour les métadonnées concernées.

## 6. Partie web

Le dossier `web/` est réservé à l’interface web. Aucune pile technique n’est encore choisie ; ne pas en présumer une sans demande explicite. Ses contraintes de départ figurent dans [web/README.md](web/README.md) :

- Consommer le moteur de `cli/` (JSON `--json` ou `ft_moulinette.engine.run()`) plutôt que dupliquer les contrôles ; ne pas modifier le schéma JSON sans examiner les intégrations éditeur.
- Le moteur exécute du code C et des Makefiles non confinés : un service exposé à du code non fiable exige un confinement séparé.
- Une exécution complète est longue et lance de nombreux processus : prévoir un traitement asynchrone.

Les livrables de `cli/` (`install.sh`, `package.sh`) n’incluent pas `web/`.

## 7. Validation

Depuis le dossier `cli/` :

```sh
python3 -m unittest discover -s tests -v
node --check integrations/vscode/extension.js
sh -n install.sh package.sh
```

Pour isoler un domaine, la découverte conserve le dossier des tests dans les imports :

```sh
python3 -m unittest discover -s tests -p 'test_printf.py' -v
python3 -m unittest discover -s tests -p 'test_regressions.py' -v
python3 -m unittest discover -s tests -p 'test_install.py' -v
```

| Tests | Ce qu’ils vérifient |
| --- | --- |
| `test_engine.py`, `test_harnesses.py` | Couverture des fonctions, compilation des bancs, erreurs, crashes et timeouts |
| `test_oracles.py`, `references.py` | Références, messages d’échec et rejet de mutations incorrectes |
| `test_full_project.py` | 43 fonctions, prototypes, véritable archive et 44 reconstructions source/header |
| `test_build_audit.py`, `test_regressions.py` | Flags manquants, archive vide, nettoyage sans effet, globales static, mémoire et nettoyage de lstmap |
| `test_printf.py` | Douze groupes, sources imbriquées, JSON, archive, NUL, retours, mutations, crashes/timeouts et fuite |
| `test_diagnostics.py`, `test_failure_messages.py`, `test_report.py` | Emplacements, messages utiles, présentation et distinction des problèmes |
| `test_install.py` | Installation/mise à jour, alias, chemins complexes et autonomie après suppression des sources |
| `test_reviewed.py` | Compatibilité de l’option masquée, sans effacement des erreurs ni persistance |

Les tests d’installation utilisent des dossiers personnels temporaires. Ne pas lancer `install.sh` sur la configuration réelle de l’utilisateur pour valider une modification de documentation.

### Dernière validation observée : 25 novembre 2026, après le passage à `cli/` + `web/`

Commandes lancées depuis `cli/` :

- `python3 -m unittest discover -s tests` : **43 tests exécutés, 43 réussis, aucun ignoré**, en environ 53 secondes. Valgrind 3.25.1 démarre désormais (`valgrind --quiet /bin/true` renvoie 0) : les tests mémoire Libft et Printf ont donc réellement été exécutés.
- `node --check integrations/vscode/extension.js` : réussi.
- `sh -n install.sh package.sh` : réussi.
- `bin/ft-moulinette --help` lancé depuis un autre dossier : réussi.
- `sh package.sh` sur une copie temporaire : l’archive contient `bin`, `ft_moulinette`, `install.sh`, `integrations`, `package.sh`, `pyproject.toml`, `README.md` à sa racine.
- Chargement et interactions graphiques Neovim/VSCode/CLion : non vérifiés. Plugins et archive de distribution du dépôt non reconstruits.

Un bilan précédent, dans un environnement où Valgrind ne démarrait pas (redirection `memcmp` introuvable dans `ld-linux-x86-64.so.2`), donnait 1 échec (`test_printf.PrintfTests.test_memory_reference_and_leak`) et 2 tests ignorés. Le test mémoire Printf ne vérifie toujours que la présence de l’exécutable Valgrind, et non son démarrage, avant de s’exécuter. Lors d’une nouvelle intervention, relancer les vérifications nécessaires et remplacer ce bilan si de nouvelles preuves sont disponibles.

## 8. Avancement et prochaines étapes possibles

| Domaine | État du code | Limite ou travail restant |
| --- | --- | --- |
| CLI, texte et JSON | Implémentés | Maintenir les contrats consommés par les éditeurs |
| Libft 43 fonctions | Bancs, prototypes, allocations et archive implémentés | La suite finie ne couvre pas tous les programmes possibles |
| Printf 12 groupes | Tests binaires, libc, archive et isolation implémentés | Hors périmètre détaillé plus haut |
| Makefile | Règles, effets, flags, relink et reconstructions implémentés | Audit PATH contournable par chemins absolus ou outils différents |
| Installation locale | Script et test d’installation présents ; test passé | Bash/Zsh pour les alias ; intégrations conservées séparément |
| Éditeurs | Intégrations et scripts de build présents | Validation graphique à effectuer dans chaque éditeur |
| Documentation | README et présent guide rédigés | Actualiser au fil des changements réels |
| Web | Dossier `web/` et contraintes initiales en place | Choisir la pile, définir le périmètre et l’isolation de l’exécution |

Pistes de travail, à entreprendre seulement si elles correspondent à une demande :

1. Vérifier plus finement les contrôles de fuite et de dépassement mémoire, maintenant que la suite passe avec un Valgrind fonctionnel.
2. Harmoniser la condition de disponibilité du test mémoire Printf avec les tests de régression, tout en conservant un vrai test des douze groupes lorsque Valgrind fonctionne.
3. Effectuer une réception graphique des trois intégrations : projet incomplet, fichier seul, erreur de compilation, correction et relance.
4. Clarifier et harmoniser les versions et la génération des livrables avant une nouvelle distribution.
5. Étendre les bancs à partir de régressions démontrées ou de nouvelles versions de sujet, avec des attentes explicites et des tests de référence.

Ne pas déclarer ces étapes terminées sans preuve. Ne pas élargir implicitement le périmètre à d’autres projets 42 ou à une plateforme supplémentaire.
