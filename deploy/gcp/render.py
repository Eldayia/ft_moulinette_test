#!/usr/bin/env python3
"""Rend service.yaml.template : chaque ${VARIABLE} doit exister dans l'environnement et avoir une forme sûre.

Usage : render.py TEMPLATE > service.yaml. Échoue si une variable manque ou si une valeur pourrait
injecter du YAML (saut de ligne, deux-points suivi d'espace, guillemet, etc.).
"""
import os
import re
import sys

PLACEHOLDER = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)\}')
SAFE = re.compile(r'^[A-Za-z0-9@:/._+-]*$')
MAY_BE_EMPTY = {'EXECUTIONS_DISABLED'}
DIGEST = re.compile(r'^[a-z0-9.-]+(:[0-9]+)?/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}$')


def render(text, environ, allow_tag=False):
    errors = []

    def substitute(match):
        name = match.group(1)
        value = environ.get(name)
        if value is None or (value == '' and name not in MAY_BE_EMPTY):
            errors.append(f'variable manquante : {name}')
            return ''
        if not SAFE.match(value):
            errors.append(f'valeur refusée pour {name} : {value!r}')
            return ''
        if name == 'RUNNER_IMAGE' and not allow_tag and not DIGEST.match(value):
            errors.append('RUNNER_IMAGE doit être une référence par digest (…@sha256:…), voir build.sh --push')
        return value
    rendered = PLACEHOLDER.sub(substitute, text)
    if errors:
        raise ValueError('\n'.join(sorted(set(errors))))
    return rendered


def main(argv):
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != '--allow-tag'):
        print('usage : render.py TEMPLATE [--allow-tag]', file=sys.stderr)
        return 2
    with open(argv[1], encoding='utf-8') as handle:
        text = handle.read()
    try:
        sys.stdout.write(render(text, os.environ, allow_tag=len(argv) == 3))
    except ValueError as exc:
        print(f'Erreur de rendu :\n{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
