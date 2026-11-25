"""Explain diagnostics from external tools; retain their original output separately."""
import re

NORM = {
    'TOO_MANY_LINES': 'La fonction dépasse 25 lignes. Isole une opération dans une fonction auxiliaire.',
    'TOO_MANY_FUNCS': 'Ce fichier contient plus de cinq définitions de fonctions.',
    'TOO_MANY_VARS_FUNC': 'La fonction déclare plus de cinq variables locales.',
    'TOO_MANY_ARGS': 'La fonction reçoit plus de quatre paramètres.',
    'LINE_TOO_LONG': 'La ligne dépasse 80 colonnes.',
    'SPACE_REPLACE_TAB': 'Remplace les espaces d’indentation par une tabulation.',
    'DECL_ASSIGN_LINE': 'Sépare la déclaration de la variable et son affectation.',
    'VAR_DECL_START_FUNC': 'Place les déclarations de variables au début de la fonction.',
    'NL_AFTER_VAR_DECL': 'Ajoute une ligne vide après les déclarations.',
    'INVALID_HEADER': 'Vérifie l’en-tête 42 au début du fichier.',
    'FORBIDDEN_CS': 'Cette structure de contrôle est interdite par la norme.',
}


def explain(check, status, raw, details):
    phase = check.removeprefix('archive:')
    if status not in ('fail', 'blocked', 'unavailable'):
        return raw
    if raw.startswith('Délai dépassé'):
        return 'Délai dépassé. Vérifie la condition d’arrêt des boucles ou relance avec un --timeout plus élevé.'
    if raw.startswith('SIG') and phase.startswith('allocation:'):
        number = phase.partition(':')[2]
        return (f'La simulation du malloc numéro {number} a interrompu le test par {raw.split()[0]}.\n'
                'Le test prévoit de faire renvoyer NULL à cette allocation. Le plantage peut survenir avant de l’atteindre.\n'
                'Piste : vérifie chaque pointeur alloué avant de le lire ou d’y écrire, puis libère les allocations précédentes si nécessaire.')
    if raw.startswith('SIG'):
        return raw.splitlines()[0] + ' Le contrôle a été interrompu avant son terme.'
    if phase == 'norm' and details:
        for detail in details:
            rule, _, original = detail['message'].partition(': ')
            detail['message'] = NORM.get(rule, 'Norminette demande de vérifier cette ligne : '+original) + ' ['+rule+']'
        return '\n'.join(f"Ligne {d['line']}, colonne {d['column']} · {d['message']}" for d in details)
    if phase in ('link','compile','prototype') or phase.startswith('allocation'):
        missing = re.findall(r"undefined reference to [`‘']([^'’]+)['’]", raw)
        if missing:
            source = 'libft.a' if check.startswith('archive:') else 'les objets compilés'
            return ('Le test appelle un symbole introuvable dans '+source+' : '+', '.join(dict.fromkeys(missing))+
                    '. Vérifie sa définition, son nom et l’inclusion du fichier objet dans la bibliothèque.')
    if phase == 'prototype':
        reason = next((line for line in raw.splitlines() if 'error:' in line), raw)
        return 'Vérifie que libft.h déclare la fonction avec le type de retour et les paramètres du sujet.\n'+reason
    if phase == 'compile' and details:
        hints = {
            'implicit declaration': 'Déclare la fonction avec son prototype avant de l’appeler et inclus le bon header.',
            'undeclared': 'Le nom utilisé n’a pas été déclaré dans cette portée. Vérifie son orthographe et sa déclaration.',
            'conflicting types': 'La signature de la définition doit correspondre à celle du header.',
            'unused parameter': 'Ce paramètre est inutilisé. Vérifie si la fonction doit en tenir compte.',
            'unused variable': 'Cette variable est déclarée mais jamais utilisée.',
            'incompatible pointer': 'Vérifie le type du pointeur transmis et celui du paramètre attendu.',
            'No such file': 'Le fichier inclus est introuvable. Vérifie son nom et son emplacement.',
            'expected': 'Le compilateur attend un élément de syntaxe ici. Vérifie aussi la ligne précédente.',
        }
        for detail in details:
            original = detail['message']
            hint = next((text for pattern,text in hints.items() if pattern in original),
                        'La compilation s’arrête sur cette ligne. Diagnostic du compilateur')
            detail['message'] = hint+' — '+original
        return '\n'.join(f"Ligne {d['line']}, colonne {d['column']} · {d['message']}" for d in details)
    if phase == 'compile' or (phase == 'link' and 'error:' in raw):
        reason = next((line for line in raw.splitlines() if 'error:' in line), raw)
        return 'Compilation impossible. Corrige le premier diagnostic puis relance.\n'+reason
    if phase == 'memory' or phase.startswith('allocation'):
        issues = []
        patterns = [
            (r'Invalid read of size (\d+)', 'Lecture de {} octet(s) à une adresse invalide. Vérifie les bornes et la durée de vie du bloc.'),
            (r'Invalid write of size (\d+)', 'Écriture de {} octet(s) à une adresse invalide. Vérifie la taille allouée et le dernier indice écrit.'),
            (r'Invalid free\(', 'Libération invalide. Passe à free le début d’un bloc alloué encore vivant.'),
            (r'(?:Conditional jump or move depends on|Use of) uninitialised value', 'Le programme utilise une valeur avant son initialisation.'),
            (r'(\d[\d,]*) bytes? in .*? (?:are|is) definitely lost', 'Fuite de mémoire : {} octet(s) définitivement perdus. Vérifie les libérations sur ce chemin.'),
            (r'(\d[\d,]*) bytes? in .*? (?:are|is) indirectly lost', 'Fuite indirecte : {} octet(s) accessibles depuis un autre bloc perdu.'),
            (r'(\d[\d,]*) bytes? in .*? (?:are|is) still reachable', '{} octet(s) restent alloués à la fin du test.'),
            (r'(\d[\d,]*) bytes? in .*? (?:are|is) possibly lost', 'Valgrind signale {} octet(s) potentiellement perdus.'),
        ]
        boundary = re.search(r'is (\d+) bytes? (after|before) a block of size (\d+)', raw)
        if boundary:
            distance, side, size = boundary.groups()
            if side == 'after':
                issues.append(f'Bloc de {size} octets : accès à l’indice {int(size)+int(distance)}.')
            else:
                issues.append(f'Accès {distance} octet(s) avant le début du bloc de {size} octets.')
        for pattern, explanation in patterns:
            match = re.search(pattern, raw)
            if match:
                # Only the access stack precedes Address. The stack after Address
                # describes allocation/free and must not be blamed for the access.
                stack = re.split(r'\bAddress\b|\n==\d+==\s*\n', raw[match.end():], maxsplit=1)[0]
                frame = re.search(r'\b(ft_\w+\.c:\d+)\)', stack)
                issues.append(explanation.format(*match.groups()) + (' ('+frame[1]+')' if frame else ''))
        if issues:
            return '\n'.join(issues)
        if 'valgrind:' in raw or raw.startswith('=='):
            return 'Le contrôle mémoire a signalé une anomalie. Consulte la première trace dans --verbose.\n'+raw
    if phase.startswith('make:') or phase == 'commands':
        error = next((line for line in raw.splitlines() if any(s in line for s in ('error:', 'No rule', 'cannot', 'Error ', 'Erreur '))),raw)
        return 'La commande make '+(phase.partition(':')[2] or 'all')+' a échoué.\n'+error
    if phase == 'link':
        return 'Impossible de construire le programme de test avec la bibliothèque.\n'+raw
    if phase == 'allocation' and status == 'unavailable':
        return 'Impossible de construire le test qui simule un échec de malloc.\n'+raw
    if phase == 'archive':
        return 'La bibliothèque attendue est libft.a à la racine. Vérifie que make la crée et que ar t libft.a liste les objets.\n'+raw
    if phase == 'relink':
        return 'Un second make sans modification doit réussir et laisser les objets et libft.a intacts.\n'+raw
    if phase == 'symbols' and status == 'unavailable':
        return 'La moulinette ne peut pas inspecter les symboles de l’objet avec nm.\n'+raw
    if phase == 'norm' and status == 'fail':
        return 'Norminette a signalé un problème dans ce fichier. Consulte son diagnostic ci-dessous.\n'+raw
    if phase == 'allocation:baseline':
        return 'Le test témoin doit réussir avant la simulation des pannes malloc.\n'+raw
    return raw
