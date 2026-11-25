"""Compact human-readable report. JSON retains individual check records."""
from collections import Counter, defaultdict
from pathlib import Path
import os
import shutil
import sys
import re
import textwrap


def check_label(check):
    labels = {
        'memory:tool': 'disponibilité de Valgrind', 'functional': 'test fonctionnel',
        'memory': 'contrôle mémoire', 'compile': 'compilation', 'norm': 'norme',
        'readme': 'titres des sections', 'readme:first-line': 'première ligne',
        'relink': 'seconde exécution de make', 'link': 'liaison du programme de test',
        'prototype': 'déclaration de la fonction dans le header', 'symbols': 'variables et fonctions autorisées',
        'archive': 'contenu de la bibliothèque', 'structure': 'emplacement des fichiers',
        'allocation': 'simulation d’une panne malloc', 'allocation:baseline': 'allocation témoin',
        'flags': 'options de compilation', 'commands': 'commandes exécutées par make',
        'archiver': 'outil de création de la bibliothèque', 'presence': 'présence du fichier',
        'make': 'contrôles du Makefile',
    }
    prefixes = {'rebuild': 'reconstruction après modification de', 'make': 'exécution de make',
                'postcondition': 'fichiers présents après make', 'allocation': 'échec simulé du malloc numéro'}
    if check in labels:
        return labels[check]
    category, _, value = check.partition(':')
    if category in ('functional', 'memory'):
        return f'{labels[category]} · {value}'
    return f'{prefixes[category]} {value}' if category in prefixes else check


def render(rows, target, verbose=False, subject='libft'):
    target = Path(target).resolve()
    root = target if target.is_dir() else target.parent
    counts = Counter(row['status'] for row in rows)
    labels = {'fail': ('en échec', 'en échec'), 'missing': ('manquant', 'manquants'),
              'blocked': ('bloqué', 'bloqués'), 'unavailable': ('indisponible', 'indisponibles'),
              'pass': ('réussi', 'réussis'), 'skip': ('ignoré', 'ignorés'),
              'manual': ('à vérifier manuellement', 'à vérifier manuellement'),
              'reviewed': ('validé manuellement', 'validés manuellement')}
    styled = sys.stdout.isatty() and 'NO_COLOR' not in os.environ and os.environ.get('TERM') != 'dumb'
    width = max(24, min(shutil.get_terminal_size().columns, 92))

    def style(text, codes):
        return f'\033[{codes}m{text}\033[0m' if styled else text

    name = 'Printf' if subject == 'printf' else 'Libft'
    title = name if target.name.lower() == name.lower() else f'{name} · {target.name}'
    lines = [style(title, '1;36'), '─' * min(width, 48)]
    problems = defaultdict(dict)
    missing = []
    for row in rows:
        try:
            file = Path(row['file']).relative_to(root)
        except ValueError:
            file = Path(row['file'])
        status = row['status']
        if status == 'missing':
            missing.append(str(file))
        if status not in ('fail', 'blocked', 'unavailable'):
            continue
        check = row['check']
        message = row['message']
        assertion = re.search(r"Assertion `(.+?)' failed", message)
        if check == 'memory:tool':
            message = message.splitlines()[0]
        elif check.removeprefix('archive:') == 'memory' and (write := re.search(
                r'Invalid write of size (\d+)\n([^\n]*)\n(?:(?![^\n]*Invalid )[^\n]*\n)*?[^\n]*?is 0 bytes after a block of size (\d+)', message)):
            size = int(write.group(3))
            location = re.search(r'\(([^()]+:\d+)\)', write.group(2))
            where = f' ({location.group(1)})' if location else ''
            message = (f'Écriture hors limites{where}. Le bloc contient {size} octets.\n'
                       f'Obtenu : écriture de {write.group(1)} octet(s) à l’indice {size}, juste après le bloc.')
            if size:
                message += f'\nPiste : le dernier indice valide est {size - 1}.'
        elif (check.removeprefix('archive:') == 'memory'
              and 'Conditional jump or move depends on uninitialised value(s)' in message):
            stack = message.split('Conditional jump or move depends on uninitialised value(s)', 1)[1].split('\n', 2)
            location = re.search(r'\(([^()]+:\d+)\)', stack[1]) if len(stack) > 1 else None
            where = f' ({location.group(1)})' if location else ''
            message = f'Une condition dépend d’une valeur qui n’a pas encore été initialisée{where}.'
            if file.name == 'ft_calloc.c':
                message += '\nPiste : initialise les n × size octets du bloc sans tester leur contenu.'
            message += '\nRapport Valgrind complet : --verbose'
        elif assertion:
            message = 'Le programme a interrompu le test sur une assertion. Vérifie la condition dans --verbose.'
        elif check == 'make:fclean' and 'No such file or directory' in message and 'rm:' in message:
            message = 'make fclean échoue en supprimant des fichiers déjà absents.\nUtilise rm -f dans les recettes clean et fclean pour pouvoir relancer le nettoyage.'
        elif check == 'relink' and row.get('raw_message', message).lstrip().startswith('ar '):
            message = 'Après un premier build, un second make relance ar sans changement de source.\nFais dépendre all de $(NAME), place la commande ar dans la règle $(NAME): $(OBJS) et retire $(NAME) des cibles .PHONY.'
        elif check.startswith('rebuild:'):
            message = 'La modification de ' + check.split(':', 1)[1] + ' n’a pas entraîné la reconstruction attendue.\nVérifie les prérequis des objets qui utilisent ce fichier (par exemple %.o: %.c libft.h). Voir --verbose pour la sortie de make.'
        elif row.get('diagnostics'):
            message = '\n'.join(f"Ligne {d['line']}, colonne {d['column']} · {d['message']}" for d in row['diagnostics'])
        key = (status, check.removeprefix('archive:'), message)
        problems[file].setdefault(key, []).append(check)
    total = sum(len(entries) for entries in problems.values()) + len(missing)
    point_label = 'point' if total == 1 else 'points'
    lines.append(style(f'◆  {total} {point_label} à examiner'  if total else '✓  Aucun problème détecté parmi les contrôles exécutés',
                       '1;33' if total else '1;32'))
    lines.append('   '+'  ·  '.join(f'{counts[s]} {label[counts[s] != 1]}' for s, label in labels.items() if counts[s]))
    if problems:
        for file, entries in problems.items():
            lines.extend(['', style(f'▸ {file}' if str(file) != '.' else '▸ Environnement de test', '1')])
            for (status, check, message), checks in entries.items():
                context = ' · sources et libft.a' if check in checks and 'archive:'+check in checks else (' · libft.a' if checks[0].startswith('archive:') else '')
                label = check_label(check)
                lines.append('  '+style(f'{label}{context}' if status == 'fail' else f'{labels[status][0]} · {label}{context}', '3'))
                for part in (message.splitlines() or ['Consulter le rapport détaillé.'])[:5]:
                    for segment in textwrap.wrap(part, width=width-5, max_lines=4, placeholder=' …'):
                        for prefix, codes in [('Essai :', '1'), ('Attendu :', '1;32'), ('Obtenu :', '1;31'), ('Piste :', '1;36')]:
                            if segment.startswith(prefix):
                                segment = style(prefix, codes) + segment[len(prefix):]
                                break
                        lines.append('  │ '+segment)
                if len(message.splitlines()) > 5:
                    lines.append('    … suite du diagnostic dans --verbose')
    if missing:
        lines.extend(['', style(f'○  Fichiers à implémenter ou à ajouter ({len(missing)})', '1;33')])
        lines.extend(textwrap.wrap(', '.join(missing), width=width, initial_indent='  ', subsequent_indent='  '))
    if verbose:
        lines.extend(['', 'Détail des contrôles'])
        for row in rows:
            try:
                file = Path(row['file']).relative_to(root)
            except ValueError:
                file = Path(row['file'])
            lines.append(f"  {file}:{row['line']}  {row['status']}  [{row['check']}]")
            lines.extend('    '+line for line in row.get('raw_message', row['message']).splitlines())
    else:
        lines.extend(['', style('Détails de chaque contrôle : relancer avec --verbose', '3')])
    return '\n'.join(lines)
