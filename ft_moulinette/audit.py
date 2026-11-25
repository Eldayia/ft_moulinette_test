"""Inspect actual tool invocations via PATH shims during a clean make."""
import json
import os
import shutil
import sys


def audit_build(project, work, execute, add, timeout, subject='libft'):
    tools=work/'audit-tools'
    tools.mkdir(exist_ok=True)
    log=work/'commands.jsonl'
    for tool in ('cc','gcc','clang','ar','libtool'):
        real=shutil.which(tool)
        script=tools/tool
        script.write_text('#!'+sys.executable+'\nimport os,sys,json\nwith open('+repr(str(log))+',"a") as f: f.write(json.dumps({"tool":'+repr(tool)+',"args":sys.argv[1:]})+"\\n")\n'+('os.execv('+repr(real)+',['+repr(real)+']+sys.argv[1:])\n' if real else 'sys.exit(127)\n'))
        script.chmod(0o755)
    execute(['make','fclean'],project,timeout)
    code,out=execute(['env','PATH='+str(tools)+os.pathsep+os.environ.get('PATH',''),'make','all'],project,timeout)
    if code:
        add('Makefile','commands','blocked',out); return
    records=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    compiles=[r for r in records if r['tool'] in ('cc','gcc','clang') and any(a.endswith('.c') for a in r['args'])]
    if not compiles:
        add('Makefile','flags','unavailable','Aucune compilation interceptée (chemin absolu ou outil différent)')
    else:
        errors=[]
        for r in compiles:
            if r['tool']!='cc': errors.append('Compilateur attendu : cc')
            missing = sorted({'-Wall','-Wextra','-Werror'}.difference(r['args']))
            if missing: errors.append('Ajoute les options manquantes à la compilation : '+' '.join(missing))
            if subject == 'libft' and '-std=c99' in r['args']: errors.append('-std=c99 interdit par le sujet')
        add('Makefile','flags','fail' if errors else 'pass','; '.join(dict.fromkeys(errors)) or 'cc et flags obligatoires observés')
    names={r['tool'] for r in records}
    add('Makefile','archiver','fail' if 'libtool' in names else ('pass' if 'ar' in names else 'unavailable'),'libtool interdit' if 'libtool' in names else ('ar observé' if 'ar' in names else 'Archivage non intercepté'))
