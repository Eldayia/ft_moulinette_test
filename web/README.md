# ft-moulinette — interface web

Interface web **locale** de la moulinette : choisis un projet Libft ou ft_printf, lance les contrôles, suis leur avancement en direct et lis le rapport dans le navigateur, avec filtres par statut, recherche et regroupement par fichier.

Elle ne refait aucun contrôle : chaque exécution appelle la CLI de [`../cli/`](../cli/) avec `--json`. Les résultats sont donc identiques à ceux du terminal et des intégrations éditeur. Version : **0.1.0**. Python 3.10+, bibliothèque standard uniquement, aucune étape de build côté navigateur.

## Lancer

Depuis le dossier `web/` du dépôt :

```sh
./bin/ft-moulinette-web
```

Puis ouvrir <http://127.0.0.1:8042/>. Le lanceur fonctionne depuis n’importe quel dossier, et `python3 -m ft_moulinette_web` depuis `web/` fait de même.

| Option | Défaut | Effet |
| --- | --- | --- |
| `--port N` | `8042` | Port d’écoute ; `0` choisit un port libre |
| `--host ADRESSE` | `127.0.0.1` | Adresse d’écoute ; hors boucle locale, `--allow-remote` est exigé |
| `--engine CHEMIN` | voir ci-dessous | Exécutable `ft-moulinette` à utiliser |
| `--allow-remote` | Désactivé | Accepte une écoute réseau et désactive le contrôle de l’en-tête `Host` |
| `--history FICHIER` | `$XDG_STATE_HOME/ft-moulinette-web/history.json` | Fichier d’historique ; sans `XDG_STATE_HOME`, `~/.local/state/…` |
| `--no-history` | Désactivé | Ne conserve pas l’historique sur disque |
| `-q`, `--quiet` | Désactivé | Ne journalise pas les requêtes |

Ctrl-C ou SIGTERM (`kill`, gestionnaire de services) arrête proprement le serveur : l’exécution en cours est annulée et l’historique enregistré.

Le moteur est cherché dans cet ordre : `--engine`, le lanceur `../cli/bin/ft-moulinette` du dépôt, puis `ft-moulinette` dans le `PATH` (par exemple après `sh install.sh`). La commande retenue est affichée au démarrage.

Avec pip, dans un environnement virtuel : `pip install -e ../cli -e .`, puis `ft-moulinette-web`.

## Utilisation

1. Indiquer un chemin **absolu** (ou commençant par `~`) : dossier du projet, ou un fichier `.c`/`.h` pour le mode fichier.
2. Choisir le projet, ou laisser la détection automatique, et les contrôles : Norminette, Valgrind, Makefile et archive. Itérations, graine et délai se trouvent dans les réglages avancés.
3. Le rapport affiche d’abord les problèmes (`fail`, `missing`, `blocked`, `unavailable`, plus `manual`). Les pastilles de statut servent de filtres, et « Tout afficher » montre aussi les réussites et les contrôles ignorés.
4. Pendant l’exécution, la page affiche le nombre de contrôles effectués, leurs statuts et les problèmes déjà détectés, puis le rapport complet à la fin.
5. La commande CLI équivalente est affichée, avec un bouton pour la copier et reproduire le résultat dans un terminal.

Les exécutions passent **une par une**, dans l’ordre d’envoi, et peuvent être annulées. Le navigateur retient les derniers réglages et les chemins récents.

## Historique

Les exécutions terminées (réussies, en erreur ou annulées), rapports compris, sont enregistrées après chaque fin d’exécution et rechargées au démarrage. Le fichier contient au plus les 50 plus récentes. Le bouton **Supprimer** retire une exécution terminée.

- Le fichier contient les chemins testés et les diagnostics : il est créé avec les droits `600`, dans un dossier `700`.
- L’écriture est atomique (fichier temporaire, puis renommage) : un arrêt brutal ne laisse pas de fichier à moitié écrit.
- Un fichier illisible n’est pas écrasé : il est renommé en `history.json.corrompu` et un avertissement s’affiche au démarrage et dans la page.
- Les entrées invalides sont ignorées. Une exécution rechargée peut viser un chemin qui n’existe plus : « Relancer » repasse alors par la validation et affiche l’erreur.
- Si l’écriture échoue (disque plein, droits), le serveur continue et la page signale que l’historique n’est pas enregistré.

## Sécurité

Le moteur compile et exécute le code C et le Makefile testés **avec tes droits**. Sa copie temporaire n’est pas un sandbox. Le serveur se protège donc des requêtes venant d’autres sites :

- écoute sur `127.0.0.1` par défaut, et refus d’une autre adresse sans `--allow-remote` ;
- refus des en-têtes `Host` autres que `localhost`, `127.0.0.1` ou `[::1]` avec le bon port (DNS rebinding) ;
- refus des `POST`/`DELETE` dont l’`Origin` ou le `Sec-Fetch-Site` désigne un autre site ;
- corps JSON obligatoire (64 Kio au plus), ce qui empêche les formulaires HTML d’autres sites d’envoyer une requête ;
- en-têtes `Content-Security-Policy` stricts, liste fermée de fichiers statiques et aucun HTML construit à partir des messages.

`--allow-remote` expose l’exécution de code à quiconque atteint le port. Ne l’utilise que derrière un confinement séparé (conteneur, utilisateur dédié, limites de ressources), que ce dépôt ne fournit pas.

## API

| Méthode et chemin | Effet |
| --- | --- |
| `POST /api/runs` | Corps `{target, project?, norm?, memory?, build?, iterations?, seed?, timeout?}`. Validation immédiate (400 avec `error` en cas de refus), puis `202` avec l’exécution en file |
| `GET /api/runs` | `runs` : historique, du plus récent au plus ancien, sans les rapports complets ; `history` : `enabled` et `error` éventuelle |
| `GET /api/runs/<id>` | État `queued`, `running`, `done`, `error` ou `cancelled`. Pendant l’exécution, `progress` (`count`, `summary`) et `partial` (problèmes déjà reçus) ; `report` contient le JSON de la CLI quand l’état vaut `done` |
| `DELETE /api/runs/<id>` | Annule une exécution en attente ou en cours |
| `DELETE /api/history/<id>` | Retire une exécution terminée de l’historique : `204`, `409` si elle est encore active, `404` si inconnue |

Dans `report.results`, chaque résultat reçoit deux champs en plus du schéma de la CLI : `label`, le libellé lisible du contrôle (issu de `ft_moulinette.report.check_label`, quand le moteur du dépôt est importable), et `relative`, le chemin relatif à la cible. Un code de sortie 1 de la CLI reste `done` : il signale des problèmes, pas une erreur du moteur.

L’avancement vient de l’option `--progress` de la CLI. Au démarrage, le serveur vérifie qu’elle figure dans `--help` du moteur. Avec un moteur plus ancien, il s’en passe et la page n’affiche qu’un indicateur d’attente.

## Développement

Depuis le dossier `web/` :

```sh
python3 -m unittest discover -s tests -v
node --check ft_moulinette_web/static/app.js
```

Les tests démarrent le serveur sur un port libre. Ils couvrent les protections HTTP, la validation, une vraie exécution Libft en mode fichier (succès et échec), l’avancement partiel, la compatibilité avec un moteur sans `--progress`, l’historique (rechargement, suppression, droits, fichier corrompu ou non inscriptible), l’arrêt par signal, l’annulation (en attente et en cours) et les erreurs du moteur, au moyen de moteurs factices.

| Fichier | Rôle |
| --- | --- |
| `ft_moulinette_web/__main__.py` | Options, choix du moteur, démarrage |
| `ft_moulinette_web/server.py` | Routes HTTP, fichiers statiques, contrôles `Host`/`Origin`, en-têtes de sécurité |
| `ft_moulinette_web/jobs.py` | Validation des demandes, file à un seul exécutant, sous-processus, annulation, annotation des rapports, historique sur disque |
| `ft_moulinette_web/static/` | Page, script et style, sans framework ni dépendance |

## Limites

- À l’annulation, le moteur reçoit SIGINT (pour nettoyer ses dossiers temporaires), puis SIGKILL au bout de 5 secondes. Une commande déjà lancée par le moteur dans sa propre session peut continuer jusqu’à son propre délai.
- L’avancement donne le nombre de contrôles effectués, pas un pourcentage : le moteur ne connaît pas leur nombre total à l’avance.
- Pas d’envoi de fichiers : la cible doit être lisible sur la machine du serveur.
- Pas d’installation par `install.sh` ni d’inclusion dans l’archive de `package.sh`.
