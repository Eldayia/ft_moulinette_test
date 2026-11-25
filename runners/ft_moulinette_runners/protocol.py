"""Protocole distant v1 (VPS → runner-api) et validation des rapports.

Le rapport ft-moulinette (schema_version 1) est transporté sans modification de structure. Tout
rapport issu d'une exécution du code soumis est traité comme non fiable : il est validé ici
(structure, types, tailles, cohérence du résumé) avant tout usage, et le résultat global est
calculé par ce module, jamais lu dans le rapport.
"""
import json
import re
from collections import Counter
from pathlib import PurePosixPath

from .base import OUTCOMES, PROJECTS, SUBMISSION_ID, ExecutionError, ExecutionResult, Options, user_error
from .limits import Limits
from .workspace import normalize_path

PROTOCOL_VERSION = 1
REPORT_SCHEMA_VERSION = 1
MODULES = {'libft': 'libft-1.3', 'printf': 'printf-1.1'}
STATUSES = ('pass', 'fail', 'missing', 'blocked', 'unavailable', 'skip', 'manual', 'reviewed')
PROBLEMS = ('fail', 'missing', 'blocked')
ROW_KEYS = {'file', 'line', 'column', 'check', 'status', 'message', 'diagnostics', 'raw_message'}
REQUIRED_ROW_KEYS = ('file', 'line', 'column', 'check', 'status', 'message')
TESTS_VERSION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$')
MAX_RESULTS = 5000
MAX_TEXT = 128 * 1024
MAX_SHORT_TEXT = 4096

def known_functions(project):
    """Fonctions connues (champ « functions »), lues dans le moteur au moment de l'appel.

    Sans le moteur (client VPS), aucune fonction n'est connue : toute sélection est refusée.
    """
    if project != 'libft':
        return ()
    try:
        from ft_moulinette.cases import FUNCTIONS
    except ImportError:
        return ()
    return tuple(FUNCTIONS)


def _protocol_error(message):
    return user_error('invalid_request', message)


# --- métadonnées de soumission ------------------------------------------------

def build_metadata(submission, limits=None):
    data = dict(protocol=PROTOCOL_VERSION, submission_id=submission.submission_id, project=submission.project,
                functions=list(submission.functions), target=submission.target,
                tests_version=submission.tests_version, options=submission.options.to_dict())
    if limits is not None:
        data['limits'] = limits.to_dict()
    return data


def parse_metadata(data, service_limits):
    """Valide les métadonnées reçues. Retourne (champs normalisés, limites effectives)."""
    if not isinstance(data, dict):
        raise _protocol_error('Métadonnées : objet JSON attendu.')
    allowed = {'protocol', 'submission_id', 'project', 'functions', 'target', 'tests_version', 'options', 'limits'}
    unknown = set(data) - allowed
    if unknown:
        raise _protocol_error('Champs inconnus : ' + ', '.join(sorted(unknown)))
    if data.get('protocol') != PROTOCOL_VERSION:
        raise ExecutionError('user', 'unsupported_protocol', f'Protocole {data.get("protocol")!r} non pris en charge '
                             f'(attendu : {PROTOCOL_VERSION}).')
    submission_id = data.get('submission_id')
    if not isinstance(submission_id, str) or not SUBMISSION_ID.match(submission_id):
        raise _protocol_error('submission_id : 32 caractères hexadécimaux attendus.')
    project = data.get('project')
    if project not in PROJECTS:
        raise _protocol_error('project : libft ou printf attendu.')
    functions = data.get('functions') or []
    if not isinstance(functions, list) or not all(isinstance(f, str) for f in functions):
        raise _protocol_error('functions : liste de noms attendue.')
    known = known_functions(project)
    unknown_functions = [f for f in functions if f not in known]
    if unknown_functions:
        raise _protocol_error('Fonctions inconnues : ' + ', '.join(unknown_functions[:10]))
    if functions:
        raise ExecutionError('user', 'unsupported', 'La sélection de fonctions n’est pas encore prise en charge '
                             'par le moteur : envoyer une liste vide.')
    tests_version = data.get('tests_version')
    if tests_version is not None and (not isinstance(tests_version, str) or not TESTS_VERSION.match(tests_version)):
        raise _protocol_error('tests_version invalide.')
    target = data.get('target')
    if target is not None:
        target = normalize_path(target, service_limits)
        if not target.endswith(('.c', '.h')):
            raise _protocol_error('target : fichier .c ou .h attendu.')
    options = Options.from_dict(data.get('options'))
    try:
        limits = service_limits.narrowed(data.get('limits'))
    except ValueError as exc:
        raise _protocol_error(str(exc)) from None
    return dict(submission_id=submission_id, project=project, functions=[], target=target,
                tests_version=tests_version, options=options), limits


# --- rapports ----------------------------------------------------------------

def _text(value, name, limit=MAX_TEXT):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'{name} : texte attendu (au plus {limit} caractères)')
    return value


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10 ** 9:
        raise ValueError(f'{name} : entier positif attendu')
    return value


def validate_report(report, project=None, limits=None):
    """Valide un rapport ft-moulinette non fiable. Retourne le rapport ; lève ValueError sinon."""
    limits = limits or Limits()
    if not isinstance(report, dict):
        raise ValueError('rapport : objet attendu')
    encoded = json.dumps(report, ensure_ascii=False).encode()
    if len(encoded) > limits.max_report_bytes:
        raise ValueError(f'rapport trop grand : {len(encoded)} octets (maximum {limits.max_report_bytes})')
    if set(report) != {'schema_version', 'module', 'summary', 'results'}:
        raise ValueError('rapport : champs inattendus ou manquants')
    if report['schema_version'] != REPORT_SCHEMA_VERSION:
        raise ValueError('rapport : schema_version non pris en charge')
    if report['module'] not in MODULES.values() or (project and report['module'] != MODULES[project]):
        raise ValueError('rapport : module inattendu')
    results = report['results']
    if not isinstance(results, list) or len(results) > MAX_RESULTS:
        raise ValueError('rapport : liste de résultats invalide')
    for index, row in enumerate(results):
        where = f'résultat {index}'
        if not isinstance(row, dict) or not set(row) <= ROW_KEYS or any(k not in row for k in REQUIRED_ROW_KEYS):
            raise ValueError(f'{where} : champs invalides')
        _text(row['file'], where + '.file', MAX_SHORT_TEXT)
        _integer(row['line'], where + '.line')
        _integer(row['column'], where + '.column')
        _text(row['check'], where + '.check', 256)
        if any(ord(char) < 32 for char in row['check']):
            raise ValueError(where + '.check : caractères de contrôle')
        if row['status'] not in STATUSES:
            raise ValueError(f'{where}.status inconnu')
        _text(row['message'], where + '.message')
        if 'raw_message' in row:
            _text(row['raw_message'], where + '.raw_message')
        if 'diagnostics' in row:
            diagnostics = row['diagnostics']
            if not isinstance(diagnostics, list) or len(diagnostics) > 200:
                raise ValueError(where + '.diagnostics invalide')
            for item in diagnostics:
                if (not isinstance(item, dict) or not {'file', 'line', 'column'} <= set(item)
                        or not set(item) <= {'file', 'line', 'column', 'message'}):
                    raise ValueError(where + '.diagnostics : entrée invalide')
                _text(item['file'], where + '.diagnostics.file', MAX_SHORT_TEXT)
                if 'message' in item:
                    _text(item['message'], where + '.diagnostics.message')
                _integer(item['line'], where + '.diagnostics.line')
                _integer(item['column'], where + '.diagnostics.column')
    summary = report['summary']
    expected = dict(Counter(row['status'] for row in results))
    if not isinstance(summary, dict) or summary != expected:
        raise ValueError('rapport : résumé incohérent avec les résultats')
    return report


def relativize_report(report, root):
    """Chemins sous la racine de la soumission → chemins relatifs (le VPS ne voit jamais /submission)."""
    root = PurePosixPath(root)

    def rewrite(value):
        path = PurePosixPath(value)
        if path == root:
            return '.'
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return value
    for row in report['results']:
        row['file'] = rewrite(row['file'])
        for item in row.get('diagnostics', []):
            item['file'] = rewrite(item['file'])
    return report


def _category(check):
    return check.removeprefix('archive:').split(':', 1)[0]


COMPILATION_CHECKS = ('compile', 'link')
MEMORY_CHECKS = ('memory',)
NORM_CHECKS = ('norm',)


def classify(report):
    """Résultat global, par priorité : compilation, tests, mémoire, norme ; jamais de faux succès.

    Un analyseur demandé mais indisponible (statut « unavailable ») empêche « success » : le
    résultat est alors « unsupported », pour ne pas présenter un contrôle non exécuté comme réussi.
    """
    rows = report['results']
    problems = [row for row in rows if row['status'] in PROBLEMS]
    categories = {_category(row['check']) for row in problems}
    if any(row['status'] == 'blocked' for row in problems) or categories & set(COMPILATION_CHECKS):
        return 'compilation_error'
    if categories - set(MEMORY_CHECKS) - set(NORM_CHECKS):
        return 'test_failure'
    if categories & set(MEMORY_CHECKS):
        return 'memory_error'
    if categories & set(NORM_CHECKS):
        return 'norm_error'
    if any(row['status'] == 'unavailable' for row in rows):
        return 'unsupported'
    return 'success'


def analyzers(report, options):
    """Analyseurs réellement exécutés et analyseurs demandés mais indisponibles."""
    used, unavailable = set(), set()
    for row in report['results']:
        category = _category(row['check'])
        name = {'norm': 'norminette', 'memory': 'valgrind', 'allocation': 'malloc-failure',
                'functional': 'functional', 'compile': 'compiler', 'make': 'make'}.get(category)
        if name is None:
            if row['check'] == 'commands' and row['status'] == 'unavailable':
                unavailable.add('build-audit')
            continue
        if row['status'] == 'unavailable':
            unavailable.add(name)
        elif row['status'] != 'skip':
            used.add(name)
    if not options.norm:
        used.discard('norminette')
    if not options.memory:
        used.discard('valgrind')
    return sorted(used - unavailable), sorted(unavailable)


# --- réponse du runner ---------------------------------------------------------

def build_response(result):
    return dict(protocol=PROTOCOL_VERSION, **result.to_dict())


def parse_response(data, submission_id, project, limits=None):
    """Valide la réponse du runner (non fiable : elle transporte un rapport issu du code soumis)."""
    if not isinstance(data, dict) or data.get('protocol') != PROTOCOL_VERSION:
        raise ValueError('réponse : protocole inattendu')
    if set(data) != {'protocol', 'submission_id', 'outcome', 'report', 'metadata', 'error'}:
        raise ValueError('réponse : champs inattendus ou manquants')
    if data['submission_id'] != submission_id:
        raise ValueError('réponse : identifiant de soumission différent')
    if data['outcome'] not in OUTCOMES:
        raise ValueError('réponse : outcome inconnu')
    metadata = data['metadata']
    if not isinstance(metadata, dict) or len(json.dumps(metadata)) > 16 * 1024:
        raise ValueError('réponse : métadonnées invalides')
    error = None
    if data['error'] is not None:
        raw = data['error']
        if (not isinstance(raw, dict) or set(raw) != {'category', 'code', 'message'}
                or raw['category'] not in ('user', 'infrastructure')):
            raise ValueError('réponse : erreur invalide')
        error = ExecutionError(raw['category'], _text(raw['code'], 'error.code', 64),
                               _text(raw['message'], 'error.message', MAX_SHORT_TEXT))
    report = data['report']
    if report is not None:
        validate_report(report, project, limits)
        # Le résultat global est recalculé ici : celui du runner n'est accepté que s'il concorde.
        expected = classify(report)
        if data['outcome'] not in (expected, 'timeout', 'cancelled', 'resource_limit'):
            raise ValueError(f'réponse : outcome {data["outcome"]!r} incohérent avec le rapport ({expected!r})')
    elif data['outcome'] not in ('timeout', 'cancelled', 'resource_limit', 'infrastructure_error',
                                 'sandbox_unavailable', 'unsupported'):
        raise ValueError('réponse : rapport absent pour un résultat qui en exige un')
    return ExecutionResult(submission_id=submission_id, outcome=data['outcome'], report=report,
                           metadata=metadata, error=error)
