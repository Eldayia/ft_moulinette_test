# ft-moulinette

Moulinette locale en ligne de commande pour tester les projets **Libft 1.3** et **Printf 1.1** de 42. Elle compile le code C, exécute des tests fonctionnels, vérifie les prototypes et les symboles, contrôle le Makefile et peut lancer Valgrind et Norminette. Les résultats sont disponibles dans le terminal, en JSON et dans les éditeurs compatibles.

Version du paquet Python : **0.3.0**. Les contrôles suivent les versions des sujets prises en charge par ce dépôt, avec la norme 4.1 comme référence ; ils ne remplacent pas la correction officielle ni une relecture du sujet applicable à ton cursus.

## Sommaire

- [Prérequis](#prérequis)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Options](#options)
- [Fonctionnalités et périmètre](#fonctionnalités-et-périmètre)
- [Comprendre les résultats](#comprendre-les-résultats)
- [Intégrations éditeur](#intégrations-éditeur)
- [Mise à jour, partage et désinstallation](#mise-à-jour-partage-et-désinstallation)
- [Dépannage](#dépannage)
- [Développement](#développement)

## Prérequis

Le fonctionnement vise **Linux**, avec des outils compatibles GNU, notamment pour l’injection des échecs de `malloc`. La compatibilité macOS ou Windows natif n’est pas validée par ce dépôt.

| Outil | Nécessité | Rôle |
| --- | --- | --- |
| Python 3.10 ou supérieur | Obligatoire | Exécution de la moulinette |
| `cc` et les headers de développement C | Obligatoires | Compilation des sources et des programmes de test |
| `make` | Obligatoire pour les contrôles du projet | Exécution des règles du Makefile |
| `ar`, `nm` | Obligatoires | Création/inspection des archives et contrôle des symboles |
| Bash ou Zsh | Pour `install.sh` | Configuration automatique des alias |
| Valgrind | Optionnel | Accès mémoire invalides, libérations et fuites |
| Norminette | Optionnel | Contrôle de norme des fichiers C et headers |
| `tar` | Pour `package.sh` et l’extraction | Distribution sous forme d’archive |

Le moteur Python n’a pas de dépendance tierce à l’exécution. Valgrind et Norminette doivent être accessibles dans le `PATH` pour être utilisés. Leur absence est signalée comme `unavailable` et entraîne un code de sortie 1, sauf si le contrôle concerné est explicitement désactivé.

Vérifier les outils disponibles :

```sh
python3 --version
command -v cc make ar nm
command -v valgrind norminette
```

## Installation

### Installation recommandée, depuis le dossier du projet

Après avoir récupéré le dépôt, depuis son dossier `cli/` (ou depuis la racine d’une archive extraite, qui contient directement ces fichiers) :

```sh
cd /chemin/vers/ft_moulinette/cli
sh install.sh
```

Le script vérifie Python et les outils `cc`, `make`, `ar`, `nm`, puis :

1. Copie le moteur et son lanceur dans `~/.local/share/ft-moulinette`.
2. Crée l’exécutable `~/.local/bin/ft-moulinette`.
3. Configure les alias `moulinette` et `ft-moulinette` dans `~/.bashrc` ou `~/.zshrc`, selon `$SHELL`. Pour Zsh, `$ZDOTDIR` est respecté.

Cette installation ne demande ni `sudo`, ni téléchargement, ni installation de paquet Python. Elle modifie le fichier de configuration du shell dans un bloc délimité par les commentaires `# >>> ft-moulinette >>>` et `# <<< ft-moulinette <<<`.

Ouvre un nouveau terminal ou exécute la commande `source` affichée par l’installateur, puis :

```sh
moulinette --help
moulinette /chemin/vers/libft
```

La copie installée est autonome : le dossier téléchargé peut ensuite être déplacé ou supprimé. Les intégrations éditeur ne sont pas copiées par l’installateur ; conserve leur dossier si tu souhaites les configurer ou les reconstruire.

### Utilisation sans installation

Depuis le dossier `cli/` du dépôt :

```sh
python3 -m ft_moulinette /chemin/vers/libft
```

Le lanceur du dépôt fonctionne aussi depuis un autre dossier :

```sh
/chemin/vers/ft_moulinette/cli/bin/ft-moulinette /chemin/vers/libft
```

### Installation avec pip dans un environnement virtuel

Cette méthode nécessite les composants `venv` et `pip` de Python, ainsi que le backend de construction setuptools. Selon l’environnement, pip peut télécharger les dépendances de construction.

```sh
cd /chemin/vers/ft_moulinette/cli
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/ft-moulinette /chemin/vers/libft
```

Le mode `-e` utilise directement les sources du dépôt. Il faut donc conserver ce dossier. Cette méthode expose la commande `ft-moulinette` dans l’environnement virtuel ; elle ne crée pas l’alias `moulinette`.

## Utilisation

Les exemples suivants utilisent l’alias créé par `install.sh`. Tu peux le remplacer par `ft-moulinette`, le chemin absolu du lanceur ou `python3 -m ft_moulinette` depuis le dossier `cli/` du dépôt.

### Tester un projet complet

```sh
moulinette /chemin/vers/libft
moulinette /chemin/vers/ft_printf
```

Sans argument, la cible est le dossier courant :

```sh
cd /chemin/vers/libft
moulinette
```

La détection automatique choisit Printf lorsqu’elle trouve notamment `ft_printf.h` dans l’arborescence, `libftprintf.a` à la racine détectée ou une cible nommée `ft_printf.c`/`ft_printf.h`. Sinon, elle choisit Libft. Si les deux projets sont présents, indique explicitement le sujet et cible de préférence son propre dossier :

```sh
moulinette /chemin/vers/libft --project libft
moulinette /chemin/vers/ft_printf --project printf
```

### Tester un fichier pendant le développement

```sh
moulinette /chemin/vers/libft/ft_strlen.c
moulinette /chemin/vers/ft_printf/src/ft_printf.c --project printf
```

Pour **Libft**, les sources voisines à la racine sont compilées pour fournir les dépendances, mais les tests fonctionnels portent sur la fonction sélectionnée. Un fichier auxiliaire reçoit `skip` pour le contrôle fonctionnel. Cibler un header ne lance pas les tests fonctionnels des fonctions.

Pour **Printf**, la racine est le premier dossier parent contenant un `Makefile`, ou le dossier du fichier si aucun n’est trouvé. Toutes les sources C du projet sont compilées et les douze groupes de tests de `ft_printf` sont exécutés, même si la cible est un seul fichier C ou un header. Dans ce mode, la norme porte sur le fichier sélectionné.

Les contrôles de présence, de README et de Makefile sont réservés au mode dossier.

### Afficher les détails et reproduire un échec

```sh
moulinette /chemin/vers/libft --verbose
moulinette /chemin/vers/libft --seed 123 --iterations 2000
```

Conserve la cible, la graine et le nombre d’itérations pour reproduire les cas pseudo-aléatoires. `--iterations` règle les boucles aléatoires prévues par les bancs d’essai ; ce n’est pas le nombre total de tests.

### Exporter un rapport JSON

```sh
moulinette /chemin/vers/libft --json > rapport.json
```

Le rapport reste produit lorsque des contrôles échouent ; le processus renvoie alors 1. Une erreur d’utilisation renvoie 2 et ne produit pas de rapport JSON exploitable.

### Désactiver certains contrôles

```sh
moulinette /chemin/vers/libft --no-norm --no-memory
moulinette /chemin/vers/libft --no-build
```

Les désactivations explicites sont signalées par `skip`. `--no-build` désactive les contrôles du **Makefile et de son archive**, mais conserve la compilation indépendante et les tests fonctionnels.

## Options

Syntaxe : `ft-moulinette [cible] [options]`.

| Option | Défaut | Effet |
| --- | --- | --- |
| `cible` | `.` | Dossier ou fichier `.c`/`.h` existant |
| `--project auto\|libft\|printf` | `auto` | Sélection du module |
| `-v`, `--verbose` | Désactivé | Affiche chaque contrôle et son journal |
| `--json` | Désactivé | Produit le rapport structuré, à la place du texte |
| `--no-norm` | Norme activée | Désactive Norminette |
| `--no-memory` | Mémoire activée | Désactive Valgrind ; conserve les tests d’échec malloc de Libft |
| `--no-build` | Makefile activé | Désactive les contrôles Makefile et les tests contre son archive |
| `--iterations N` | `500` | Nombre d’itérations des boucles pseudo-aléatoires, entier positif |
| `--seed N` | `42` | Graine pseudo-aléatoire, normalisée sur 32 bits |
| `--timeout SECONDES` | `15` | Délai par commande ou exécution, entier positif |
| `--progress` | Désactivé | Écrit chaque résultat sur la sortie d’erreur dès sa création, une ligne JSON `{"event": "result", "result": {…}}` par résultat ; la sortie standard est inchangée |
| `-h`, `--help` | — | Affiche l’aide |

Le timeout n’est pas une limite globale : un projet déclenche de nombreuses commandes. Les exécutions des bancs sous Valgrind bénéficient d’au moins 30 secondes chacune.

## Fonctionnalités et périmètre

### Libft 1.3 : 43 fonctions

Dans la version du sujet encodée ici, **les listes chaînées font partie des fonctions obligatoires**. `ft_lstsize` retourne `unsigned int` et les fonctions de classification doivent retourner exactement `0` ou `1`.

| Famille | Fonctions, sans le préfixe `ft_` |
| --- | --- |
| Classification et casse | `isalpha`, `isdigit`, `isalnum`, `isascii`, `isprint`, `toupper`, `tolower` |
| Mémoire | `memset`, `bzero`, `memcpy`, `memmove`, `memchr`, `memcmp`, `calloc` |
| Chaînes et conversion | `strlen`, `strlcpy`, `strlcat`, `strchr`, `strrchr`, `strncmp`, `strnstr`, `atoi`, `strdup`, `substr`, `strjoin`, `strtrim`, `split`, `itoa`, `strmapi`, `striteri` |
| Écriture sur descripteur | `putchar_fd`, `putstr_fd`, `putendl_fd`, `putnbr_fd` |
| Listes | `lstnew`, `lstadd_front`, `lstsize`, `lstlast`, `lstadd_back`, `lstdelone`, `lstclear`, `lstiter`, `lstmap` |

Les contrôles incluent :

- Présence de `Makefile`, `libft.h`, `README.md` et des 43 fichiers `ft_<fonction>.c` ; sources C et headers attendus à la racine.
- Compilation indépendante avec `-Wall -Wextra -Werror`, contrôle des signatures déclarées dans le header et liaison des dépendances disponibles.
- Cas limites, chaînes vides, tailles nulles, caractères élevés, chevauchements valides, limites numériques, listes et comparaisons avec la libc lorsque le contrat le permet.
- Exécution séparée des fonctions, avec détection des crashes et dépassements de délai.
- Contrôle des variables globales, y compris `static`, des appels externes autorisés et des auxiliaires non `static`.
- Valgrind sur les cas exécutés, dont des allocations de taille exacte pour révéler certains dépassements de lecture ou d’écriture.
- Injection des pannes de `malloc` avec le linker GNU : allocations observées sur les entrées témoins, dont un `split` de trois mots ; échec des trois allocations de nœuds de `lstmap` et vérification du nettoyage des contenus.
- Tests fonctionnels, mémoire et allocations rejoués contre la véritable `libft.a` construite par le Makefile.

### Printf 1.1 : 12 groupes

Les groupes sont : texte littéral, `%c`, `%s`, `%p`, `%d`, `%i`, `%u`, `%x`, `%X`, `%%`, mélanges et cas aléatoires reproductibles.

- Comparaison du retour et de la sortie binaire exacte avec `snprintf` de la libc locale, y compris les octets NUL produits par `%c`.
- Chaînes vides, longues jusqu’à 64 Kio, UTF-8, octets élevés, limites numériques, pointeurs, appels répétés et nombreux arguments.
- Compilation des sources en sous-dossiers et des dépendances incluses dans le projet, notamment une libft embarquée.
- Vérification de `int ft_printf(const char *, ...)`, des symboles externes, des variables globales, de la norme et de la mémoire.
- Douze groupes exécutés séparément, puis rejoués contre `libftprintf.a` en mode dossier.

Le module n’impose pas de fichier principal nommé `ft_printf.c`, ni d’auxiliaires `static`. Il ne teste pas les bonus, flags, largeurs ou précisions, formats invalides, format NULL, `%s` avec NULL, erreurs d’écriture ou pannes de `malloc`. Le rendu des pointeurs suit la libc locale.

### Makefile, README et norme

En mode dossier, les deux modules vérifient :

- Les règles `all`, `clean`, `fclean`, `re` et la cible de l’archive attendue.
- La suppression effective des objets et de l’archive, ainsi que l’absence de relink lors d’un second `make` sans modification.
- La reconstruction des objets et de l’archive après modification des sources et headers.
- Les appels à `cc` avec `-Wall -Wextra -Werror`, l’utilisation de `ar` et l’interdiction de `libtool`. Pour Libft, `-std=c99` est également rejeté par le contrôle encodé.
- Les sections Markdown `Description`, `Instructions`, `Resources` et l’attribution en première ligne du README du **projet testé** :

```markdown
*This activity has been created as part of the 42 curriculum by ton_login.*
```

Norminette est lancée si elle est disponible et si le contrôle n’est pas désactivé. Sa version installée détermine les règles effectivement appliquées.

### Limites à connaître

Une suite finie ne prouve pas la conformité de tous les comportements possibles. La qualité du README, les ressources, la déclaration d’usage de l’IA, les explications d’algorithmes, les fichiers inutilisés et les exigences subjectives demandent une relecture humaine. Les rapports n’ajoutent pas de rappel de relecture systématique.

L’analyse des symboles ne couvre pas tous les appels indirects. L’audit des outils de build passe par des intercepteurs dans le `PATH` : les commandes exécutées par chemin absolu ou via d’autres outils peuvent être signalées comme non observables.

Les compilations et le Makefile s’exécutent principalement dans une copie temporaire, puis celle-ci est supprimée. **Cette copie n’est pas un sandbox de sécurité** : les liens symboliques sont préservés et le code/Makefile s’exécute avec les droits de l’utilisateur. Utilise la moulinette sur des projets de confiance.

## Comprendre les résultats

| Statut | Signification |
| --- | --- |
| `pass` | Contrôle exécuté et réussi |
| `fail` | Erreur détectée |
| `missing` | Fichier attendu absent |
| `blocked` | Contrôle impossible à exécuter, par exemple à cause d’une compilation ou liaison impossible |
| `unavailable` | Outil absent, inutilisable ou contrôle non observable |
| `skip` | Contrôle désactivé ou non applicable |

| Code de sortie | Signification |
| --- | --- |
| `0` | Aucun `fail`, `missing`, `blocked` ou `unavailable` ; certains contrôles peuvent être désactivés |
| `1` | Au moins un de ces quatre statuts est présent |
| `2` | Erreur d’arguments, cible invalide ou erreur remontée à l’analyseur de commande |

Le rapport texte regroupe les problèmes. `--verbose` affiche les contrôles individuels et leurs journaux. Les diagnostics du compilateur et de Norminette peuvent fournir les lignes et colonnes, remappées vers les fichiers originaux.

Le JSON contient :

| Champ | Contenu |
| --- | --- |
| `schema_version` | `1` |
| `module` | `libft-1.3` ou `printf-1.1` |
| `summary` | Nombre de résultats par statut présent |
| `results` | Liste des contrôles individuels |

Chaque résultat contient `file`, `line`, `column`, `check`, `status` et `message`. Selon le contrôle, `diagnostics` fournit plusieurs emplacements et `raw_message` conserve le diagnostic brut. Les identifiants préfixés par `archive:` correspondent aux tests contre l’archive du Makefile.

Avec `--progress`, les mêmes résultats sont aussi écrits un par un sur la sortie d’erreur pendant l’exécution, dans l’ordre du rapport final. L’interface web s’en sert pour afficher l’avancement.

Un code 0 signifie que les contrôles exécutés n’ont pas signalé de problème ; il ne certifie pas la conformité au sujet.

## Intégrations éditeur

Les intégrations appellent le même moteur. Configure un **chemin absolu vers un exécutable**, par exemple `/home/ton_login/.local/bin/ft-moulinette`. Un alias de shell n’est pas accessible comme exécutable depuis un éditeur.

### Neovim 0.10 ou supérieur

Ajoute le dossier `cli/integrations/neovim` du dépôt à ton `runtimepath`, puis configure le module dans `init.lua` :

```lua
vim.opt.runtimepath:append('/chemin/vers/ft_moulinette/cli/integrations/neovim')
require('ft_moulinette').setup({
  executable = vim.fn.expand('~/.local/bin/ft-moulinette'),
})
```

- `:Moulinette /chemin/vers/libft` : teste la cible, ou le dossier courant sans argument.
- `:MoulinetteFile` : teste le fichier ouvert.

Les buffers sont sauvegardés et les problèmes alimentent la quickfix. Le module utilise `vim.system`.

### VSCode 1.85 ou supérieur

Génère le paquet local sans installer de dépendance npm, depuis le dossier `cli/` :

```sh
python3 integrations/vscode/package_local.py
```

Dans VSCode, ouvre Extensions → menu `…` → **Install from VSIX**, puis sélectionne `cli/integrations/vscode/build/ft-moulinette.vsix`.

Configure le paramètre :

```json
{
  "ftMoulinette.executable": "/home/ton_login/.local/bin/ft-moulinette"
}
```

La palette propose **Moulinette: tester le projet** et **Moulinette: tester le fichier**. Les fichiers sont sauvegardés avant l’exécution ; les résultats apparaissent dans **Problems** et le canal **Moulinette** d’**Output**. Pour développer l’extension, ouvre `cli/integrations/vscode` et utilise la configuration F5 fournie.

### CLion

Le plugin propose les actions projet/fichier dans le menu **Tools** et une console dédiée. Il demande le chemin absolu du lanceur et le mémorise par projet.

Pour reconstruire le ZIP à partir du SDK d’un CLion installé, depuis le dossier `cli/` :

```sh
python3 integrations/clion/build_local.py --clion /opt/clion
```

Le résultat est `cli/integrations/clion/build/distributions/ft-moulinette-clion-0.3.0.zip`. Le script utilise le JDK et les JAR de l’installation indiquée ; il ne télécharge pas Gradle. La compatibilité du ZIP dépend du SDK utilisé pour le construire.

Consulte le [guide CLion](integrations/clion/README.md) pour l’installation depuis le disque et les vérifications dans l’éditeur. Les interactions graphiques des trois intégrations restent à valider dans leurs éditeurs respectifs.

## Mise à jour, partage et désinstallation

### Mettre à jour

Avec l’installation recommandée, récupère les nouvelles sources puis relance :

```sh
sh install.sh
```

Le script recopie les sources et remplace le bloc d’alias sans le dupliquer. Avec pip en mode éditable, les modifications Python du dépôt sont directement utilisées ; relance l’installation pip si les métadonnées changent.

### Partager une archive

Depuis le dossier `cli/` du dépôt :

```sh
sh package.sh
```

Le script crée `cli/dist/ft-moulinette.tar.gz` avec le moteur, les lanceurs, les scripts d’installation et les intégrations. Les tests de développement ne sont pas inclus. Les fichiers déjà présents dans les dossiers de build des intégrations peuvent être embarqués : reconstruis les paquets si tu souhaites les distribuer à jour.

Le destinataire peut extraire l’archive dans un nouveau dossier :

```sh
mkdir ft-moulinette
tar -xzf /chemin/vers/ft-moulinette.tar.gz -C ft-moulinette
cd ft-moulinette
sh install.sh
```

### Désinstaller

Pour l’installation par script, supprime `~/.local/bin/ft-moulinette` et `~/.local/share/ft-moulinette`, puis retire uniquement le bloc d’alias délimité `ft-moulinette` du fichier de configuration de ton shell. Ouvre ensuite un nouveau terminal. Les extensions éditeur se désinstallent séparément.

Pour pip, utilise le Python de l’environnement concerné :

```sh
.venv/bin/python -m pip uninstall ft-moulinette
```

## Dépannage

| Symptôme | Vérification ou solution |
| --- | --- |
| `moulinette: command not found` | Recharge le fichier indiqué par l’installateur ou ouvre un nouveau terminal ; teste `~/.local/bin/ft-moulinette --help` |
| L’éditeur ne trouve pas le programme | Utilise un chemin absolu, sans alias ni `~` non développé |
| Valgrind/Norminette `unavailable` | Vérifie leur présence dans le `PATH` de l’éditeur ou du terminal ; installe l’outil, ou désactive explicitement le contrôle concerné |
| Valgrind installé mais inutilisable | Relance avec `--verbose` pour lire le diagnostic de démarrage |
| Mauvais module détecté | Ajoute `--project libft` ou `--project printf` et cible le dossier du projet concerné |
| Liaison `blocked` | Lis le journal détaillé, vérifie les fichiers de dépendances et les déclarations dans le header |
| Timeout sur une commande lente | Augmente `--timeout`, par exemple `--timeout 60` ; vérifie aussi les boucles infinies |
| Audit Makefile non observable | Vérifie que les outils sont invoqués via le `PATH`, avec les noms reconnus `cc`, `gcc`, `clang`, `ar`, `libtool` |
| Shell non pris en charge par l’installateur | Utilise le lanceur du dépôt ou l’installation pip ; les alias automatiques nécessitent Bash ou Zsh |

## Développement

La carte des modules, les règles de modification et l’état d’avancement figurent dans [docs/agent-guide.md](../docs/agent-guide.md). Ce dossier `cli/` contient l’outil en ligne de commande et ses intégrations ; la partie web est développée dans [`web/`](../web/).

Depuis le dossier `cli/` :

```sh
python3 -m unittest discover -s tests -v
node --check integrations/vscode/extension.js
sh -n install.sh package.sh
```

La suite utilise `unittest`, compile des programmes C temporaires et couvre notamment les 43 fonctions Libft, les douze groupes Printf, les implémentations de référence, les mutations incorrectes, les diagnostics, le JSON, les archives et les reconstructions Makefile. Les tests mémoire concernés sont ignorés si Valgrind est absent. S’il est présent mais ne démarre pas, certains tests sont ignorés et le test mémoire Printf peut échouer ; le dernier résultat local est détaillé dans `docs/agent-guide.md`. Node.js n’est nécessaire ici que pour vérifier la syntaxe de l’extension VSCode.

Les archives générées, environnements virtuels, caches et journaux sont des artefacts locaux ignorés par Git. Leur présence ne garantit pas qu’ils correspondent aux dernières sources.
