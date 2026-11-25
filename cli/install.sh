#!/bin/sh
# Installation hors ligne depuis le dossier extrait ou cloné.
set -eu
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Erreur : Python 3.10 ou supérieur est nécessaire.' >&2
    exit 1
fi
exec python3 - "$SOURCE_DIR" <<'PY'
import os
from pathlib import Path
import re
import shlex
import shutil
import sys


def install():
    if sys.version_info < (3, 10):
        raise ValueError('Python 3.10 ou supérieur est nécessaire.')
    source = Path(sys.argv[1])
    if not (source / 'ft_moulinette' / '__main__.py').is_file():
        raise ValueError('Conserve install.sh dans le dossier complet de la moulinette.')
    missing = [tool for tool in ('cc', 'make', 'ar', 'nm') if not shutil.which(tool)]
    if missing:
        raise ValueError('Outils requis introuvables : ' + ', '.join(missing))
    shell = Path(os.environ.get('SHELL', '/bin/bash')).name
    home = Path.home()
    if shell == 'zsh':
        rc = Path(os.environ.get('ZDOTDIR') or str(home)) / '.zshrc'
    elif shell == 'bash':
        rc = home / '.bashrc'
    else:
        raise ValueError('Alias automatique : Bash ou Zsh requis (SHELL=' + shell + ').')
    destination = home / '.local' / 'share' / 'ft-moulinette'
    bindir = home / '.local' / 'bin'
    executable = bindir / 'ft-moulinette'
    launcher = destination / 'bin' / 'ft-moulinette'
    begin = '# >>> ft-moulinette >>>'
    end = '# <<< ft-moulinette <<<'
    current = rc.read_text(errors='surrogateescape') if rc.exists() else ''
    if current.count(begin) != current.count(end):
        raise ValueError('Bloc ft-moulinette incomplet dans ' + str(rc) + '.')
    # Quote twice: once for executing the path, once for the alias definition.
    block = (begin + '\n'
             + 'alias moulinette=' + shlex.quote(shlex.quote(str(executable))) + '\n'
             + 'alias ft-moulinette=' + shlex.quote(shlex.quote(str(executable))) + '\n'
             + end + '\n')
    pattern = re.escape(begin) + r'\n.*?' + re.escape(end) + r'\n?'
    if begin in current:
        updated = re.sub(pattern, lambda _: block, current, flags=re.S)
    else:
        updated = current + ('\n' if current and not current.endswith('\n') else '') + block
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('ft_moulinette', 'bin'):
        src, dst = source / name, destination / name
        if src.resolve() != dst.resolve():
            shutil.copytree(src, dst, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('README.md', 'install.sh', 'pyproject.toml'):
        src, dst = source / name, destination / name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
    bindir.mkdir(parents=True, exist_ok=True)
    executable.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' '
                          + shlex.quote(str(launcher)) + ' "$@"\n')
    executable.chmod(0o755)
    # Bash/Zsh aliases work even when ~/.local/bin is absent from PATH.
    rc.parent.mkdir(parents=True, exist_ok=True)
    if updated != current:
        rc.write_text(updated, errors='surrogateescape')
    print('Installation terminée : ' + str(destination))
    print('Alias moulinette et ft-moulinette configurés dans ' + str(rc))
    print('Pour les utiliser dans ce terminal : source ' + shlex.quote(str(rc)))
    print('Puis : moulinette /chemin/vers/libft')
    print('Tu peux maintenant déplacer ou supprimer le dossier téléchargé.')
    for tool in ('valgrind', 'norminette'):
        if not shutil.which(tool):
            print('Outil optionnel absent : ' + tool + '. Les contrôles associés seront signalés indisponibles.')


try:
    install()
except (OSError, ValueError) as exc:
    print('Erreur d’installation : ' + str(exc), file=sys.stderr)
    sys.exit(1)
PY
