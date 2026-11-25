# ft-moulinette — partie web

Dossier réservé au développement de l’interface web. Aucune pile technique n’est encore choisie ni livrée.

## Point d’appui sur le moteur

Le moteur se trouve dans [`../cli/`](../cli/). Il est conseillé de le consommer tel quel plutôt que de dupliquer ses contrôles :

- **JSON de la CLI** : `ft-moulinette <cible> --json` produit `schema_version=1`, `module`, `summary`, `results` (voir [AGENT.md](../AGENT.md), section 4). C’est le contrat déjà utilisé par les intégrations VSCode et Neovim ; toute évolution doit rester compatible avec elles.
- **Appel Python direct** : `ft_moulinette.engine.run(target, ...)` retourne la liste des résultats, à condition que `cli/` soit dans le chemin d’import (par exemple via `pip install -e ../cli`).

Points d’attention propres à un usage web :

- Le moteur compile et exécute le code C et le Makefile fournis avec les droits de l’utilisateur ; la copie temporaire **n’est pas un sandbox**. Une exposition à du code non fiable demande un confinement séparé (conteneur, utilisateur dédié, limites de ressources).
- Une exécution complète dure de l’ordre de la minute et lance de nombreux processus ; prévoir une exécution asynchrone plutôt qu’une requête bloquante.
- Préserver la distinction des statuts `pass`, `fail`, `missing`, `blocked`, `unavailable`, `skip` et les messages en français.
