#!/usr/bin/env python3
"""DOUBLE DE TEST de la CLI Cloud Run `sandbox`. N'ISOLE RIEN.

Reproduit l'interface documentée utilisée par runner_api (`do` avec --sandbox-name, --rootfs, --stdin=false,
--mount type=bind,src=…,dst=…[,readonly], --env, --workdir, puis `delete --force`) et sa sémantique de code
de sortie (0 si succès, 1 pour toute erreur ou tout code non nul de la commande). Chaque appel est consigné
dans calls.jsonl à côté du script, pour vérifier les options passées. Le moteur est exécuté directement sur
l'hôte, en traduisant les chemins de la sandbox : ce double ne valide en rien l'isolation Cloud Run.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / 'fake_config.json').read_text())


def record(entry):
    with open(HERE / 'calls.jsonl', 'a') as handle:
        handle.write(json.dumps(entry) + '\n')


def fail(message):
    print(f'sandbox: {message}', file=sys.stderr)
    sys.exit(1)


def main(argv):
    record(dict(argv=argv))
    if argv[:2] == ['delete', '--force'] and len(argv) == 3:
        sys.exit(1)  # `do` a déjà supprimé la sandbox
    if not argv or argv[0] != 'do' or '--' not in argv:
        fail('usage')
    options, command = argv[1:argv.index('--')], argv[argv.index('--') + 1:]
    mounts, env, i = {}, {}, 0
    while i < len(options):
        flag = options[i]
        if flag in ('--stdin=false',):
            i += 1
            continue
        if flag in ('--allow-egress', '--write'):
            fail(f'{flag} interdit par la politique du double de test')
        value = options[i + 1]
        if flag == '--mount':
            fields = dict(part.split('=', 1) if '=' in part else (part, True) for part in value.split(','))
            if fields.get('type') != 'bind' or '..' in value:
                fail('montage invalide')
            mounts[fields['dst']] = fields['src']
        elif flag == '--env':
            key, _, val = value.partition('=')
            env[key] = val
        elif flag not in ('--sandbox-name', '--rootfs', '--workdir'):
            fail(f'option inconnue {flag}')
        i += 2
    mode = CONFIG.get('mode', 'run')
    if mode == 'hang':
        time.sleep(300)
    if mode == 'crash':
        fail('internal error: sandbox runtime unavailable')

    def outside(arg):
        for inner, real in CONFIG['paths'].items():
            if arg == inner:
                return real
        for dst, src in mounts.items():
            if arg == dst or arg.startswith(dst + '/'):
                return src + arg[len(dst):]
        return arg
    real = [outside(arg) for arg in command]
    env.setdefault('PATH', '/usr/bin:/bin')
    completed = subprocess.run(real, stdin=subprocess.DEVNULL, capture_output=True, cwd='/tmp', env=env)
    stdout, stderr = completed.stdout, completed.stderr
    for dst, src in mounts.items():  # le moteur doit voir /submission, comme dans la vraie sandbox
        stdout = stdout.replace(src.encode(), dst.encode())
        stderr = stderr.replace(src.encode(), dst.encode())
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    sys.exit(0 if completed.returncode == 0 else 1)


if __name__ == '__main__':
    main(sys.argv[1:])
