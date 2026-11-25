#!/usr/bin/env python3
"""Validation réelle du service runner-api déployé sur Cloud Run. Lancé par smoke-test.sh.

À exécuter uniquement contre un service de validation explicitement autorisé. Les sondes sont bornées :
tentatives de connexion réseau, lecture de variables d'environnement, écriture refusée, marqueur dans /tmp.
Code de sortie 1 si une vérification essentielle échoue. Le résumé imprimé sert de preuve à reporter
dans docs/cloudrun.md.
"""
import argparse
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runners'))

from ft_moulinette_runners.base import Options, Submission  # noqa: E402
from ft_moulinette_runners.cloudrun import CloudRunRunner, IdTokenProvider  # noqa: E402
from ft_moulinette_runners.limits import Limits  # noqa: E402
from ft_moulinette_runners.workspace import build_archive  # noqa: E402

HEADER = '#include <stddef.h>\nsize_t ft_strlen(const char *s);\n'
STRLEN_OK = ('#include "libft.h"\n\nsize_t\tft_strlen(const char *s)\n{\n\tsize_t\ti;\n\n\ti = 0;\n'
             '\twhile (s[i])\n\t\ti++;\n\treturn (i);\n}\n')
STRLEN_WRONG = '#include "libft.h"\nsize_t ft_strlen(const char *s){size_t i=0;while(s[i])i++;return i+1;}\n'

PROBE = '\n'.join([
    'import os, socket, subprocess',
    'for host in (("1.1.1.1", 53), ("8.8.8.8", 443), ("169.254.169.254", 80), ("metadata.google.internal", 80)):',
    '    s = socket.socket(); s.settimeout(3)',
    '    try:',
    '        s.connect(host); print("PROBE_NET_" + "OPEN", host[0])',
    '    except OSError:',
    '        print("PROBE_NET_BLOCKED", host[0])',
    'keys = sorted(k for k in os.environ if k.startswith(("GOOGLE", "GCP", "K_", "CLOUD_RUN", "FTM_")))',
    'print("PROBE_ENV_" + ("LEAK " + ",".join(keys) if keys else "CLEAN"))',
    'for path in ("/var/run/secrets", "/run/secrets", "/usr/local/gcp"):',
    '    print("PROBE_PATH", path, "PRESENT" if os.path.exists(path) else "ABSENT")',
    'print("PROBE_UID", os.getuid())',
    'r = subprocess.run(["sh", "-c", "command -v sudo >/dev/null && sudo -n true"], capture_output=True)',
    'print("PROBE_SUDO", "YES" if r.returncode == 0 else "NO")',
    'for path in ("/submission/pwned", "/opt/ft-moulinette/pwned"):',
    '    try:',
    '        open(path, "w").close(); print("PROBE_WRITE_" + "ALLOWED", path)',
    '    except OSError:',
    '        print("PROBE_WRITE_DENIED", path)',
]) + '\n'


def makefile(lines):
    recipe = ''.join(f'\t@{line}\n' for line in lines)
    return f'NAME=libft.a\nall:\n{recipe}\t@false\nclean:\n\t@true\nfclean: clean\nre: fclean all\n.PHONY: all clean fclean re\n'


class Check:
    def __init__(self):
        self.rows = []

    def record(self, name, ok, detail='', essential=True):
        self.rows.append((name, ok, detail, essential))
        mark = 'OK ' if ok else ('ÉCHEC' if essential else 'info')
        print(f'[{mark}] {name}{" — " + detail if detail else ""}', flush=True)

    @property
    def failed(self):
        return [r for r in self.rows if r[3] and not r[1]]


def text_of(result):
    if not result.report:
        return ''
    return '\n'.join(r['message'] + '\n' + r.get('raw_message', '') for r in result.report['results'])


def token_provider(args):
    if args.key_file:
        import os
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = args.key_file
        return IdTokenProvider(args.url, 'key')

    def from_gcloud():
        command = ['gcloud', 'auth', 'print-identity-token', f'--audiences={args.url}']
        if args.impersonate:
            command.append(f'--impersonate-service-account={args.impersonate}')
        return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    return IdTokenProvider(args.url, fetcher=from_gcloud)


def main():
    parser = argparse.ArgumentParser(description='Validation réelle de runner-api sur Cloud Run')
    parser.add_argument('--url', required=True)
    parser.add_argument('--impersonate', help='compte invoker à emprunter avec gcloud (rôle Token Creator requis)')
    parser.add_argument('--key-file', help='clé JSON du compte invoker (à défaut de --impersonate)')
    args = parser.parse_args()
    check = Check()
    limits = Limits(request_timeout=120, submission_timeout=60)

    # 1. Accès anonyme refusé
    try:
        urllib.request.urlopen(args.url + '/readyz', timeout=30)
        check.record('accès anonyme refusé', False, 'HTTP 200 sans jeton')
    except urllib.error.HTTPError as exc:
        check.record('accès anonyme refusé', exc.code in (401, 403), f'HTTP {exc.code}')

    runner = CloudRunRunner(args.url, token_provider(args), limits)
    # 2. Disponibilité et capacités (démarrage à froid inclus)
    started = time.monotonic()
    health = runner.check()
    check.record('readyz (sandbox launcher actif)', health.available,
                 f'{health.detail} ({time.monotonic() - started:.1f} s, démarrage à froid possible)')
    if not health.available:
        return finish(check)
    capabilities = runner.capabilities()
    check.record('capabilities', capabilities.get('protocol') == 1 and capabilities.get('network') == 'blocked',
                 json.dumps({k: capabilities.get(k) for k in ('image_version', 'tests_version', 'ready')}))

    def submit(files, options=None, target=None):
        archive = build_archive({k: v.encode() for k, v in files.items()})
        submission = Submission('libft', archive=archive, target=target,
                                options=options or Options(norm=False, memory=False, build=True, iterations=1))
        began = time.monotonic()
        result = runner.execute(submission)
        return result, time.monotonic() - began

    # 3. Soumission minimale : compilation, tests, Norminette, Valgrind
    result, seconds = submit({'libft.h': HEADER, 'ft_strlen.c': STRLEN_OK},
                             Options(norm=True, memory=True, build=False, iterations=10), 'ft_strlen.c')
    statuses = {r['check']: r['status'] for r in (result.report or {}).get('results', [])}
    check.record('compilation', statuses.get('compile') == 'pass', f'{result.outcome}, {seconds:.1f} s')
    check.record('test fonctionnel', statuses.get('functional') == 'pass', str(statuses.get('functional')))
    check.record('Valgrind dans la sandbox', statuses.get('memory') == 'pass', str(statuses.get('memory')),
                 essential=False)
    check.record('Norminette dans la sandbox', statuses.get('norm') in ('pass', 'fail'), str(statuses.get('norm')),
                 essential=False)
    check.record('sandbox supprimée', bool(result.metadata.get('sandbox_status')),
                 str(result.metadata.get('sandbox_status')))

    # 4. Échec détecté
    result, _ = submit({'libft.h': HEADER, 'ft_strlen.c': STRLEN_WRONG}, target='ft_strlen.c')
    check.record('échec fonctionnel détecté', result.outcome == 'test_failure', result.outcome)

    # 5. Sondes d'isolation
    result, _ = submit({'libft.h': HEADER, 'ft_strlen.c': STRLEN_OK, 'probe.mk': PROBE,
                        'Makefile': makefile(['python3 probe.mk'])})
    text = text_of(result)
    check.record('réseau sortant bloqué', 'PROBE_NET_BLOCKED' in text and 'PROBE_NET_OPEN' not in text)
    check.record('serveur de métadonnées inaccessible', 'PROBE_NET_BLOCKED 169.254.169.254' in text)
    check.record('aucune variable sensible visible', 'PROBE_ENV_CLEAN' in text,
                 next((line for line in text.splitlines() if line.startswith('PROBE_ENV_')), 'sonde absente'))
    check.record('soumission et moteur en lecture seule', 'PROBE_WRITE_ALLOWED' not in text
                 and text.count('PROBE_WRITE_DENIED') >= 2)
    for line in sorted({line for line in text.splitlines() if line.startswith(('PROBE_UID', 'PROBE_SUDO', 'PROBE_PATH'))}):
        check.record('observation', True, line, essential=False)

    # 6. Pas de fuite entre deux soumissions
    marker = 'ftm-smoke-' + secrets.token_hex(8)
    submit({'libft.h': HEADER, 'ft_strlen.c': STRLEN_OK,
            'Makefile': makefile([f'touch /tmp/{marker}', 'echo MARKER_WRITTEN'])})
    result, _ = submit({'libft.h': HEADER, 'ft_strlen.c': STRLEN_OK,
                        'Makefile': makefile([f'test -e /tmp/{marker} && echo MARKER_SEEN || echo MARKER_ABSENT'])})
    text = text_of(result)
    check.record('soumissions isolées entre elles', 'MARKER_ABSENT' in text and 'MARKER_SEEN' not in text)

    # 7. Délai global et suppression après dépassement
    result, seconds = submit({'libft.h': HEADER, 'ft_strlen.c': STRLEN_OK, 'Makefile': makefile(['sleep 300'])})
    check.record('délai global appliqué', result.outcome == 'timeout' and seconds < 115,
                 f'{result.outcome} en {seconds:.0f} s, sandbox {result.metadata.get("sandbox_status")}')
    return finish(check)


def finish(check):
    print()
    if check.failed:
        print(f'{len(check.failed)} vérification(s) essentielle(s) en échec : ouverture refusée.')
        return 1
    print('Toutes les vérifications essentielles passent. Reporter ce résumé dans docs/cloudrun.md.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
