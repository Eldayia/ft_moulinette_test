"""Printf 1.1 project checks, using the shared execution/build diagnostics."""
import re
import shutil
import tempfile
from pathlib import Path

from .audit import audit_build
from .build import check_build, check_rebuilds
from .diagnostics import locations
from .printf_cases import GROUPS, HARNESS


def project_root(target):
    if target.is_dir():
        return target
    for parent in target.parents:
        if (parent/'Makefile').is_file():
            return parent
    return target.parent


def test_printf(links, work, project, execute, add, memory, iterations, seed, timeout, prefix=''):
    harness = work/'printf_test.c'
    binary = work/'printf_test'
    harness.write_text(HARNESS.replace('SEED', str(seed % (2**32))).replace('ITERATIONS', str(iterations)))
    include_dirs = sorted({project, *(p.parent for p in project.rglob('*.h'))})
    command = ['cc', '-Wall', '-Wextra', '-Werror', '-fno-builtin', '-g', '-O0']
    for directory in include_dirs:
        command.extend(['-I', str(directory)])
    code, out = execute([*command, str(harness), *map(str, links), '-o', str(binary)], work, timeout)
    add('ft_printf.h', prefix+'link', 'blocked' if code else 'pass', out or 'Banc Printf lié')
    if code:
        return
    for group in GROUPS:
        code, out = execute([str(binary), group], work, timeout)
        add('ft_printf.h', prefix+'functional:'+group, 'fail' if code else 'pass',
            f'Groupe {group}, seed={seed % (2**32)}\n'+out)
        if memory and not code:
            code, out = execute(['valgrind', '--quiet', '--leak-check=full', '--show-leak-kinds=all',
                                 '--errors-for-leak-kinds=all', '--error-exitcode=99',
                                 str(binary), group], work, max(30, timeout))
            add('ft_printf.h', prefix+'memory:'+group, 'fail' if code else 'pass', out or 'Aucune erreur mémoire')


def run_printf(target, norm=True, memory=True, iterations=500, seed=42, timeout=15, build=True):
    from .engine import execute
    target = Path(target).resolve()
    if not target.exists() or (target.is_file() and target.suffix not in ('.c', '.h')):
        raise ValueError('Indiquer un dossier ou un fichier C/header existant')
    root = project_root(target)
    rows = []
    with tempfile.TemporaryDirectory(prefix='ft-moulinette-printf-') as temp:
        work = Path(temp)
        project = work/'project'
        shutil.copytree(root, project, ignore=shutil.ignore_patterns(
            '.git', '.venv', '__pycache__', 'node_modules'), symlinks=True)

        def add(file, check, status, message):
            details = locations(message, check.removeprefix('archive:').split(':')[0], file, root, project)
            row = dict(file=str(root/file), line=1, column=1, check=check,
                       status=status, message=message.strip())
            if details:
                row.update(file=details[0]['file'], line=details[0]['line'],
                           column=details[0]['column'], diagnostics=details)
            rows.append(row)

        sources = sorted(p for p in root.rglob('*.c')
                         if not any(part.startswith('.') for part in p.relative_to(root).parts))
        if target.is_dir():
            for name in ('Makefile', 'README.md'):
                if not (root/name).is_file():
                    add(name, 'presence', 'missing', 'Fichier attendu absent')
            if not list(root.rglob('ft_printf.h')):
                add('ft_printf.h', 'presence', 'missing', 'Header ft_printf.h absent')
            if not sources:
                add('', 'presence', 'missing', 'Aucune source C')
            readme = root/'README.md'
            if readme.is_file():
                text = readme.read_text(errors='replace')
                missing = [title for title in ('Description', 'Instructions', 'Resources')
                           if not re.search(r'^#+\s+'+title+r'\s*$', text, re.I|re.M)]
                add('README.md', 'readme', 'fail' if missing else 'pass',
                    'Sections absentes : '+', '.join(missing) if missing else 'Titres présents')
                first = text.splitlines()[0] if text.splitlines() else ''
                valid = bool(re.fullmatch(
                    r'([*_])This activity has been created as part of the 42 curriculum by .+\.\1', first))
                add('README.md', 'readme:first-line', 'pass' if valid else 'fail',
                    'Attribution conforme' if valid else
                    'Première ligne attendue : *This activity has been created as part of the 42 curriculum by ton_login.*')
        if memory:
            code, out = execute(['valgrind', '--quiet', '/bin/true'], work, timeout)
            if code:
                add('', 'memory:tool', 'unavailable', 'Valgrind indisponible.\n'+out)
                memory = False
        else:
            add('', 'memory', 'skip', 'Contrôles mémoire désactivés')

        include_dirs = sorted({project, *(p.parent for p in project.rglob('*.h'))})
        includes = [arg for directory in include_dirs for arg in ('-I', str(directory))]
        objects = []
        for index, source in enumerate(sources):
            file = str(source.relative_to(root))
            obj = work/f'source_{index}.o'
            code, out = execute(['cc', '-Wall', '-Wextra', '-Werror', '-fno-builtin',
                                 '-g', '-O0', *includes, '-c', str(project/file), '-o', str(obj)],
                                work, timeout)
            add(file, 'compile', 'fail' if code else 'pass', out or 'Compilation réussie')
            if not code:
                objects.append((file, obj))
        defined = set()
        symbol_tables = []
        for file, obj in objects:
            code, out = execute(['nm', str(obj)], work, timeout)
            symbol_tables.append((file, code, out))
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[-2] in ('T', 'W'):
                    defined.add(parts[-1])
        allowed = {'malloc', 'free', 'write', '__stack_chk_fail', '_GLOBAL_OFFSET_TABLE_'}
        for file, code, out in symbol_tables:
            errors = []
            for line in out.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                kind, symbol = parts[-2:]
                if kind in ('B', 'D', 'C', 'G', 'S', 'b', 'd', 'g', 's'):
                    errors.append('Variable globale : '+symbol)
                if kind == 'U' and symbol not in allowed | defined:
                    errors.append('Fonction externe interdite : '+symbol)
            add(file, 'symbols', 'unavailable' if code else ('fail' if errors else 'pass'),
                out if code else ('; '.join(errors) or 'Symboles conformes'))

        prototype = work/'prototype.c'
        prototype.write_text('#include "ft_printf.h"\n'
                             'void check_declared(void) {(void)&ft_printf;}\n'
                             'int ft_printf(const char *, ...);\n'
                             'int (*check_signature)(const char *, ...) = ft_printf;\n')
        code, out = execute(['cc', '-Wall', '-Wextra', '-Werror', *includes,
                             '-fsyntax-only', str(prototype)], work, timeout)
        add('ft_printf.h', 'prototype', 'fail' if code else 'pass', out or 'Signature conforme')
        if len(objects) == len(sources) and objects:
            dependencies = work/'dependencies.a'
            code, out = execute(['ar', 'rcs', str(dependencies),
                                 *(str(obj) for _, obj in objects)], work, timeout)
            if code:
                add('', 'link', 'blocked', out)
            else:
                test_printf([dependencies], work, project, execute, add, memory, iterations, seed, timeout)
        else:
            add('', 'functional', 'blocked', 'Compilation des sources impossible')

        if norm:
            files = [*sources, *sorted(root.rglob('*.h'))] if target.is_dir() else [target]
            if not shutil.which('norminette'):
                add('', 'norm', 'unavailable', 'Norminette absente')
            else:
                for source in files:
                    code, out = execute(['norminette', str(source)], work, timeout)
                    add(str(source.relative_to(root)), 'norm', 'fail' if code else 'pass', out)
        else:
            add('', 'norm', 'skip', 'Norminette désactivée')

        if target.is_dir() and build and (project/'Makefile').is_file():
            archive_name = 'libftprintf.a'
            check_build(project, execute, add, timeout, archive_name)
            audit_build(project, work, execute, add, timeout, 'printf')
            archive = project/archive_name
            if archive.is_file():
                before = {p: p.stat().st_mtime_ns for p in project.rglob('*') if p.suffix in ('.o', '.a')}
                code, out = execute(['make'], project, timeout)
                after = {p: p.stat().st_mtime_ns for p in project.rglob('*') if p.suffix in ('.o', '.a')}
                add('Makefile', 'relink', 'fail' if code or before != after else 'pass',
                    out or 'Pas de relink')
                check_rebuilds(project, execute, add, timeout, archive_name)
                code, out = execute(['ar', 't', str(archive)], work, timeout)
                add('Makefile', 'archive', 'fail' if code or not out.strip() else 'pass',
                    out or 'Archive vide')
                test_printf([archive], work, project, execute, add, memory, iterations, seed, timeout, 'archive:')
            else:
                add('Makefile', 'archive', 'fail', 'libftprintf.a absent à la racine')
        elif target.is_dir() and not build:
            add('', 'make', 'skip', 'Contrôles Makefile désactivés')
    return rows
