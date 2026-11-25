"""Normalisation des méthodes de soumission (ZIP, fichiers avec chemins relatifs, code collé) en une archive.

Le VPS ne fait que lire, valider et empaqueter : aucun fichier soumis n'est écrit sur disque, compilé
ni interprété ici. La validation est celle de ft_moulinette_runners.workspace (revalidée par le runner).
"""
import json

from ft_moulinette_runners.base import Options, user_error
from ft_moulinette_runners.limits import Limits
from ft_moulinette_runners.workspace import build_archive, normalize_path, read_archive

SOURCES = ('archive', 'files', 'pasted')


def parse_options(raw):
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        raise user_error('invalid_options', 'Options : JSON invalide.') from None
    return Options.from_dict(data)


def archive_from_zip(data, limits):
    files = read_archive(data, limits)
    return build_archive(files, limits), len(files)


def archive_from_files(contents, paths, limits):
    """contents : liste d'octets ; paths : liste de chemins relatifs (même ordre), envoyée par le navigateur."""
    if len(contents) != len(paths):
        raise user_error('invalid_request', 'Chaque fichier doit avoir un chemin relatif.')
    if len(contents) > limits.max_files:
        raise user_error('too_many_files', f'Trop de fichiers (maximum {limits.max_files}).')
    files = {}
    for path, content in zip(paths, contents):
        if not isinstance(path, str):
            raise user_error('invalid_path', 'Chemin de fichier invalide.')
        files[path] = content
    return build_archive(files, limits), len(files)


def archive_from_pasted(raw, limits):
    """raw : JSON {"chemin": "contenu"} (code collé dans l'éditeur)."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise user_error('invalid_request', 'Code collé : JSON invalide.') from None
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise user_error('invalid_request', 'Code collé : objet {chemin: contenu} attendu.')
    files = {path: content.encode() for path, content in data.items()}
    return build_archive(files, limits), len(files)


def check_target(target, archive, limits):
    if not target:
        return None
    target = normalize_path(target, limits)
    if not target.endswith(('.c', '.h')):
        raise user_error('invalid_path', 'Le fichier ciblé doit être un .c ou un .h.')
    if target not in read_archive(archive, limits):
        raise user_error('invalid_path', f'Fichier ciblé absent de la soumission : {target}')
    return target


def default_limits():
    return Limits()
