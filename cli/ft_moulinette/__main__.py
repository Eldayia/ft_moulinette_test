import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from .engine import run, detect_project
from .report import render


def main():
    p=argparse.ArgumentParser(description='Moulinette Libft 1.3 — 43 fonctions — et Printf 1.1')
    p.add_argument('--project', choices=('auto', 'libft', 'printf'), default='auto',
                   help='Sujet à tester (détection automatique par défaut)')
    p.add_argument('target',nargs='?',default='.')
    p.add_argument('-v','--verbose',action='store_true',help='Afficher chaque contrôle et son journal')
    p.add_argument('--reviewed', action='append', choices=('readme', 'project', 'all'),
                   default=[], help=argparse.SUPPRESS)
    p.add_argument('--json',action='store_true')
    p.add_argument('--no-norm',action='store_true')
    p.add_argument('--no-memory',action='store_true')
    p.add_argument('--no-build',action='store_true')
    p.add_argument('--iterations',type=int,default=500)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--timeout',type=int,default=15)
    p.add_argument('--progress',action='store_true',
                   help='Écrire chaque résultat sur stderr dès sa création, une ligne JSON par résultat')
    args=p.parse_args()
    if args.iterations<1 or args.timeout<1: p.error('iterations et timeout doivent être positifs')
    def progress(row):
        print(json.dumps(dict(event='result',result=row),ensure_ascii=False),file=sys.stderr,flush=True)
    try: rows=run(args.target,not args.no_norm,not args.no_memory,args.iterations,args.seed,args.timeout,not args.no_build,args.project,
                  progress if args.progress else None)
    except (ValueError,OSError) as exc: p.error(str(exc))
    for row in rows:
        if row['status'] != 'manual' or row['check'] != 'review':
            continue
        category = 'readme' if Path(row['file']).name == 'README.md' else 'project'
        if 'all' in args.reviewed or category in args.reviewed:
            row['status'] = 'reviewed'
            row['message'] = 'Relecture déclarée effectuée par l’utilisateur. ' + row['message']
    counts=dict(Counter(r['status'] for r in rows))
    subject = detect_project(args.target, args.project)
    if args.json: print(json.dumps(dict(schema_version=1,module='printf-1.1' if subject == 'printf' else 'libft-1.3',summary=counts,results=rows),ensure_ascii=False,indent=2))
    else:
        print(render(rows,args.target,args.verbose,subject))
    return 1 if any(r['status'] in ('fail','missing','blocked','unavailable') for r in rows) else 0

if __name__=='__main__': raise SystemExit(main())
