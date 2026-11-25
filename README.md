# ft-moulinette

Moulinette locale pour les projets **Libft 1.3** et **Printf 1.1** de 42.

| Dossier | Contenu |
| --- | --- |
| [`cli/`](cli/) | Moteur Python, lanceur, tests, scripts d’installation et d’archive, intégrations Neovim/VSCode/CLion |
| [`web/`](web/) | Interface web locale : lancement des contrôles et rapport interactif dans le navigateur |

- Installation et utilisation de l’outil en ligne de commande : [cli/README.md](cli/README.md).
- Interface web : [web/README.md](web/README.md).
- Fonctionnement interne, conventions et état du dépôt : [docs/agent-guide.md](docs/agent-guide.md).
- Exécution distante sur Google Cloud Run (en cours) : mission dans [AGENT.md](AGENT.md), état et plan dans [docs/cloudrun.md](docs/cloudrun.md).

Démarrage rapide :

```sh
cd cli
sh install.sh
moulinette /chemin/vers/libft

# ou, dans le navigateur : http://127.0.0.1:8042/
../web/bin/ft-moulinette-web
```
