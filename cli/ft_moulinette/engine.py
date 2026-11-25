import os
import re
import signal
import shutil
import subprocess
import tempfile
from pathlib import Path
from .prototypes import PROTOTYPES
from .runner import test_function
from .explain import explain
from .audit import audit_build
from .build import check_build, check_rebuilds
from .diagnostics import locations
from .cases import FUNCTIONS, CASES, PRELUDE, ALLOCATIONS, WRAP, LSTMAP_FAILURE


def execute(args, cwd, timeout=15):
    with tempfile.TemporaryFile() as output:
        try:
            p = subprocess.Popen(args, cwd=cwd, stdout=output, stderr=output, start_new_session=True)
        except OSError as exc:
            return 127, str(exc)
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            code = 124
        output.seek(0)
        text = output.read(65536).decode(errors='replace')
        if code < 0:
            name = signal.Signals(-code).name
            reason = 'accès mémoire invalide' if name == 'SIGSEGV' else 'arrêt du processus'
            text = f'{name} — {reason}.\n' + text
        elif code and not text.strip():
            text = f'Le processus a quitté avec le code {code} sans diagnostic.'
        return code, ('Délai dépassé\n' if code == 124 else '') + text


def detect_project(target, subject='auto'):
    if subject not in ('auto', 'libft', 'printf'):
        raise ValueError('Projet attendu : auto, libft ou printf')
    if subject != 'auto':
        return subject
    target = Path(target).resolve()
    root = target if target.is_dir() else target.parent
    if target.is_file():
        from .printf import project_root
        candidate = project_root(target)
        if list(candidate.rglob('ft_printf.h')) or (candidate/'libftprintf.a').exists():
            return 'printf'
    if list(root.rglob('ft_printf.h')) or (root/'libftprintf.a').exists() or target.name in ('ft_printf.c', 'ft_printf.h'):
        return 'printf'
    return 'libft'


def run(target, norm=True, memory=True, iterations=500, seed=42, timeout=15, build=True, subject='auto', progress=None):
    """progress, s'il est fourni, reçoit chaque résultat dès sa création."""
    subject = detect_project(target, subject)
    if subject == 'printf':
        from .printf import run_printf
        return run_printf(target, norm, memory, iterations, seed, timeout, build, progress)
    seed = seed % (2 ** 32)
    target = Path(target).resolve()
    if not target.exists() or (target.is_file() and target.suffix not in ('.c', '.h')):
        raise ValueError('Indiquer un dossier ou un fichier C/header existant')
    root = target if target.is_dir() else target.parent
    results = []
    project = None
    def add(file, check, status, message):
        details = locations(message, check, file, root, project) if project is not None else []
        row = dict(file=str(root / file), line=1, column=1, check=check, status=status, message=message.strip())
        if details: row.update(file=details[0]['file'], line=details[0]['line'], column=details[0]['column'], diagnostics=details)
        explanation = explain(check, status, message.strip(), details)
        if explanation != row['message']:
            row['raw_message'] = row['message']
            row['message'] = explanation
        results.append(row)
        if progress is not None:
            progress(row)
    selected = sorted(root.glob('*.c')) if target.is_dir() else ([target] if target.suffix == '.c' else [])
    with tempfile.TemporaryDirectory(prefix='ft-moulinette-') as temp:
        work = Path(temp)
        memory_requested = memory
        if memory:
            code, output = execute(['valgrind', '--quiet', '/bin/true'], work, timeout)
            if code:
                add('', 'memory:tool', 'unavailable',
                    'Valgrind ne peut pas démarrer. Les contrôles mémoire n’ont pas été exécutés.\n'+output)
                memory = False
        project = work / 'project'
        shutil.copytree(root, project, ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__', 'node_modules'), symlinks=True)
        if target.is_dir():
            for name in ['Makefile','libft.h','README.md'] + ['ft_'+f+'.c' for f in FUNCTIONS]:
                if not (root/name).is_file(): add(name,'presence','missing','Fichier attendu absent')
            for file in root.rglob('*'):
                if any(p.startswith('.') for p in file.relative_to(root).parts): continue
                if file.suffix in ('.c','.h') and file.parent != root:
                    add(str(file.relative_to(root)), 'structure', 'fail', 'Les sources doivent être à la racine')
            readme = root/'README.md'
            if readme.exists():
                text = readme.read_text(errors='replace')
                required = ('Description', 'Instructions', 'Resources')
                missing = [title for title in required if not re.search(r'^#+\s+'+title+r'\s*$', text, re.I|re.M)]
                add('README.md','readme','fail' if missing else 'pass',
                    'Titres attendus introuvables : '+', '.join(missing)+'. Vérifie les titres Markdown de tes sections.' if missing else 'Titres présents')
                first=text.splitlines()[0] if text.splitlines() else ''
                valid=bool(re.fullmatch(r'([*_])This activity has been created as part of the 42 curriculum by .+\.\1',first))
                example='*This activity has been created as part of the 42 curriculum by ton_login.*'
                add('README.md','readme:first-line','pass' if valid else 'fail',
                    'Attribution conforme' if valid else 'Ligne lue : '+(first or '(vide)')+'\nFormat attendu : '+example+' (remplace ton_login par ton identifiant)')
        objects = {}
        for source in sorted(root.glob('*.c')):
            obj = work/(source.stem+'.o')
            code,out=execute(['cc','-Wall','-Wextra','-Werror','-fno-builtin','-g','-O0','-I',str(project),'-c',str(project/source.name),'-o',str(obj)],work,timeout)
            if source in selected: add(source.name,'compile','fail' if code else 'pass',out or 'Compilation réussie')
            if code: continue
            objects[source.stem]=obj
            if source not in selected: continue
            name=source.stem.removeprefix('ft_')
            status,symbols=execute(['nm',str(obj)],work,timeout)
            allowed=set()
            if name in ALLOCATIONS or name=='lstmap': allowed.add('malloc')
            if name in ('split','lstdelone','lstclear','lstmap'): allowed.add('free')
            if name.endswith('_fd'): allowed.add('write')
            invalid=[]
            for line in symbols.splitlines():
                parts=line.split()
                if len(parts)<2: continue
                kind,symbol=parts[-2:]
                if kind in ('B','D','C','G','S','b','d','g','s'): invalid.append('Variable globale : '+symbol)
                if kind=='U' and not symbol.startswith('ft_') and symbol not in allowed and symbol not in ('__stack_chk_fail','_GLOBAL_OFFSET_TABLE_'):
                    invalid.append('Fonction externe interdite : '+symbol)
                if kind=='T' and symbol!=source.stem: invalid.append('Fonction auxiliaire non static : '+symbol)
            add(source.name,'symbols','unavailable' if status else ('fail' if invalid else 'pass'),symbols if status else ('; '.join(invalid) or 'Symboles conformes'))
        archive=work/'dependencies.a'
        execute(['ar','rcs',str(archive),*map(str,objects.values())],work,timeout)
        for source in selected:
            name=source.stem.removeprefix('ft_')
            if name not in CASES:
                add(source.name,'functional','skip','Fichier auxiliaire'); continue
            if source.stem not in objects:
                add(source.name,'functional','blocked','Compilation impossible'); continue
            prototype=work/'prototype.c'
            prototype.write_text('#include "libft.h"\nvoid check_declared(void){(void)&ft_'+name+';}\n'+PROTOTYPES[name]+';\n')
            code,out=execute(['cc','-Wall','-Wextra','-Werror','-I',str(project),'-fsyntax-only',str(prototype)],work,timeout)
            add(source.name,'prototype','fail' if code else 'pass',out or 'Signature conforme')
            test_function(name,source.name,[objects[source.stem],archive],work,project,execute,add,memory,iterations,seed,timeout)
        if norm:
            files=sorted(root.rglob('*.c'))+sorted(root.rglob('*.h')) if target.is_dir() else [target]
            files=[f for f in files if not any(p.startswith('.') for p in f.relative_to(root).parts)]
            if not shutil.which('norminette'): add('','norm','unavailable','Norminette absent')
            else:
                for file in files:
                    code,out=execute(['norminette',str(file)],work,timeout)
                    add(str(file.relative_to(root)),'norm','fail' if code else 'pass',out)
        else: add('','norm','skip','Norminette désactivée')
        if not memory_requested: add('','memory','skip','Contrôles mémoire désactivés')
        if target.is_dir() and build and (project/'Makefile').exists():
            check_build(project,execute,add,timeout)
            audit_build(project,work,execute,add,timeout)
            archive=project/'libft.a'
            if archive.exists():
                before={str(p):p.stat().st_mtime_ns for p in project.rglob('*') if p.suffix in ('.o','.a')}
                code,out=execute(['make'],project,timeout)
                after={str(p):p.stat().st_mtime_ns for p in project.rglob('*') if p.suffix in ('.o','.a')}
                add('Makefile','relink','fail' if code or before!=after else 'pass',out or ('Un objet ou libft.a a été modifié.' if before!=after else 'Pas de relink'))
                check_rebuilds(project,execute,add,timeout)
                for source in selected:
                    name=source.stem.removeprefix('ft_')
                    if name in CASES:
                        test_function(name,source.name,[archive],work,project,execute,add,memory,iterations,seed,timeout,'archive:')
                code,out=execute(['ar','t',str(archive)],work,timeout)
                add('Makefile','archive','fail' if code else 'pass',out)
            else: add('Makefile','archive','fail','libft.a absent')
        elif target.is_dir() and not build: add('','make','skip','Contrôles Makefile désactivés')
    return results
