import argparse
import shutil
import sys
from pathlib import Path

from .jobs import REPO_CLI
from .server import Server, is_loopback


def engine_command(executable=None):
    """Commande du moteur : --engine, sinon le cli/ du dépôt, sinon ft-moulinette du PATH."""
    if executable:
        path = Path(executable).expanduser()
        if not path.is_file():
            raise ValueError(f'Moteur introuvable : {path}')
        return [str(path.resolve())]
    launcher = REPO_CLI / 'bin' / 'ft-moulinette'
    if launcher.is_file():
        return [sys.executable, str(launcher)]
    found = shutil.which('ft-moulinette')
    if found:
        return [found]
    raise ValueError('Moteur introuvable : indiquer --engine /chemin/vers/ft-moulinette.')


def main(argv=None):
    p = argparse.ArgumentParser(prog='ft-moulinette-web', description='Interface web locale de ft-moulinette')
    p.add_argument('--host', default='127.0.0.1', help='Adresse d’écoute (127.0.0.1 par défaut)')
    p.add_argument('--port', type=int, default=8042, help='Port d’écoute (8042 par défaut, 0 pour un port libre)')
    p.add_argument('--engine', help='Exécutable ft-moulinette à utiliser')
    p.add_argument('--allow-remote', action='store_true',
                   help='Autoriser une écoute hors boucle locale (le code testé n’est pas confiné)')
    p.add_argument('-q', '--quiet', action='store_true', help='Ne pas journaliser les requêtes')
    args = p.parse_args(argv)
    if not 0 <= args.port <= 65535:
        p.error('port invalide')
    if not is_loopback(args.host) and not args.allow_remote:
        p.error('écoute hors boucle locale refusée : le moteur exécute les Makefiles et le code testés '
                'sans confinement. Ajouter --allow-remote en connaissance de cause.')
    try:
        engine = engine_command(args.engine)
        server = Server((args.host, args.port), engine, args.allow_remote)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    server.quiet = args.quiet
    host = f'[{args.host}]' if ':' in args.host else args.host
    print(f'ft-moulinette-web : http://{host}:{server.server_address[1]}/', flush=True)
    print('Moteur : ' + ' '.join(engine), flush=True)
    print('Ctrl-C pour arrêter.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
