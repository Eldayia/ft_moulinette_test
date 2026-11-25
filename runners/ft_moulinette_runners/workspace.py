"""Préparation, validation et extraction sûres des fichiers soumis.

Toutes les méthodes de soumission (dossier, fichiers multiples, code collé, ZIP) sont normalisées en une
archive ZIP déterministe. L'archive est revalidée par chaque partie (VPS et runner) : rien n'y est cru
sur parole, ni les noms, ni les tailles déclarées, ni les types de fichiers.
"""
import hashlib
import io
import os
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from .base import user_error
from .limits import Limits

SOURCE_SUFFIXES = ('.c', '.h', '.md', '.mk')
MAKEFILE_NAMES = ('Makefile', 'makefile', 'GNUmakefile')
SKIPPED_DIRECTORIES = ('.git', '.venv', '__pycache__', 'node_modules')
FIXED_TIMESTAMP = (2000, 1, 1, 0, 0, 0)  # archive reproductible : même contenu, même empreinte


def is_allowed_name(name):
    return name in MAKEFILE_NAMES or name.endswith(SOURCE_SUFFIXES)


def normalize_path(raw, limits):
    """Chemin relatif POSIX sûr, normalisé NFC. Lève une erreur utilisateur sinon."""
    if not isinstance(raw, str) or not raw:
        raise user_error('invalid_path', 'Nom de fichier vide.')
    if any(ord(char) < 32 or char in '\\\x7f' for char in raw):
        raise user_error('invalid_path', f'Nom de fichier invalide : {raw!r}')
    if raw.startswith('/') or (len(raw) > 1 and raw[1] == ':'):
        raise user_error('invalid_path', f'Chemin absolu refusé : {raw!r}')
    path = unicodedata.normalize('NFC', raw)
    parts = path.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise user_error('invalid_path', f'Chemin refusé (composant vide, « . » ou « .. ») : {raw!r}')
    if len(path.encode()) > limits.max_path_length or len(parts) > limits.max_path_depth:
        raise user_error('invalid_path', f'Chemin trop long ou trop profond : {raw!r}')
    if any(part in SKIPPED_DIRECTORIES for part in parts[:-1]):
        raise user_error('invalid_path', f'Dossier non accepté dans une soumission : {raw!r}')
    if not is_allowed_name(parts[-1]):
        raise user_error('unexpected_file', f'Type de fichier non accepté : {raw!r} '
                         '(acceptés : .c, .h, .md, .mk, Makefile).')
    return path


def _check_unique(paths):
    seen = {}
    for path in paths:
        key = path.casefold()
        if key in seen:
            raise user_error('duplicate_path', f'Noms en double après normalisation : {seen[key]!r} et {path!r}')
        seen[key] = path
    # Un fichier ne peut pas aussi être un dossier (« a » et « a/b.c »).
    files = set(seen)
    for key in files:
        parent = PurePosixPath(key).parent
        while str(parent) != '.':
            if str(parent) in files:
                raise user_error('duplicate_path', f'Un fichier et un dossier portent le même nom : {parent}')
            parent = parent.parent


def _check_totals(sizes, limits):
    if len(sizes) > limits.max_files:
        raise user_error('too_many_files', f'Trop de fichiers : {len(sizes)} (maximum {limits.max_files}).')
    if not sizes:
        raise user_error('empty_submission', 'La soumission ne contient aucun fichier accepté.')
    total = sum(sizes)
    if total > limits.max_uncompressed_bytes:
        raise user_error('too_large', f'Taille totale trop grande : {total} octets '
                         f'(maximum {limits.max_uncompressed_bytes}).')


def build_archive(files, limits=None):
    """{chemin relatif: octets} → archive ZIP déterministe, après validation complète."""
    limits = limits or Limits()
    normalized = {}
    for raw, content in files.items():
        if not isinstance(content, (bytes, bytearray)):
            raise TypeError('contenu attendu en octets')
        path = normalize_path(raw, limits)
        if path in normalized:  # deux noms distincts, identiques après normalisation NFC
            raise user_error('duplicate_path', f'Noms en double après normalisation : {raw!r}')
        if len(content) > limits.max_file_bytes:
            raise user_error('file_too_large', f'Fichier trop grand : {path} ({len(content)} octets, '
                             f'maximum {limits.max_file_bytes}).')
        normalized[path] = bytes(content)
    _check_unique(list(normalized))
    _check_totals([len(c) for c in normalized.values()], limits)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(normalized):
            info = zipfile.ZipInfo(path, FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, normalized[path])
    data = buffer.getvalue()
    if len(data) > limits.max_upload_bytes:
        raise user_error('too_large', f'Archive trop grande : {len(data)} octets (maximum {limits.max_upload_bytes}).')
    return data


def pack_directory(directory, limits=None):
    """Archive un dossier local sans suivre les liens. Retourne (archive, fichiers ignorés)."""
    limits = limits or Limits()
    root = Path(directory)
    if not root.is_dir():
        raise user_error('invalid_path', f'Dossier introuvable : {root}')
    files, skipped = {}, []
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories
                                if d not in SKIPPED_DIRECTORIES and not (Path(current) / d).is_symlink())
        for name in sorted(names):
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode) or not is_allowed_name(name):
                skipped.append(relative)
                continue
            if path.lstat().st_size > limits.max_file_bytes:
                raise user_error('file_too_large', f'Fichier trop grand : {relative}')
            if len(files) >= limits.max_files:
                raise user_error('too_many_files', f'Trop de fichiers (maximum {limits.max_files}).')
            files[relative] = path.read_bytes()
    return build_archive(files, limits), skipped


def pack_file(path, limits=None):
    """Mode fichier : archive le dossier parent ; retourne (archive, ignorés, chemin relatif ciblé)."""
    path = Path(path)
    archive, skipped = pack_directory(path.parent, limits)
    return archive, skipped, path.name


def read_archive(data, limits=None):
    """Valide une archive ZIP reçue et retourne {chemin normalisé: octets}.

    Les tailles sont vérifiées pendant la décompression (bombes ZIP), les liens symboliques,
    fichiers spéciaux, entrées chiffrées et noms dangereux sont refusés.
    """
    limits = limits or Limits()
    if not isinstance(data, (bytes, bytearray)):
        raise user_error('invalid_archive', 'Archive attendue.')
    if len(data) > limits.max_upload_bytes:
        raise user_error('too_large', f'Archive trop grande : {len(data)} octets (maximum {limits.max_upload_bytes}).')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError, OSError):
        raise user_error('invalid_archive', 'Archive ZIP illisible.') from None
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_files * 4:  # dossiers compris ; borne avant toute lecture
            raise user_error('too_many_files', 'Archive avec trop d’entrées.')
        raw_names = [info.filename for info in infos]
        if len(set(raw_names)) != len(raw_names):
            raise user_error('duplicate_path', 'Entrées en double dans l’archive.')
        files, budget = {}, limits.max_uncompressed_bytes
        for info in infos:
            mode = info.external_attr >> 16
            if info.flag_bits & 0x1:
                raise user_error('invalid_archive', f'Entrée chiffrée refusée : {info.filename!r}')
            if mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise user_error('invalid_archive', f'Lien ou fichier spécial refusé : {info.filename!r}')
            if info.is_dir():
                name = info.filename.rstrip('/')
                if name:
                    for part in name.split('/'):
                        if part in ('', '.', '..') or part in SKIPPED_DIRECTORIES:
                            raise user_error('invalid_path', f'Dossier refusé : {info.filename!r}')
                continue
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise user_error('invalid_archive', f'Méthode de compression non acceptée : {info.filename!r}')
            path = normalize_path(info.filename, limits)
            if path in files:  # deux entrées distinctes, identiques après normalisation NFC
                raise user_error('duplicate_path', f'Noms en double après normalisation : {info.filename!r}')
            if info.file_size > limits.max_file_bytes:
                raise user_error('file_too_large', f'Fichier trop grand : {path}')
            if len(files) >= limits.max_files:
                raise user_error('too_many_files', f'Trop de fichiers (maximum {limits.max_files}).')
            cap = min(limits.max_file_bytes, budget)
            try:
                with archive.open(info) as handle:
                    content = handle.read(cap + 1)
            except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, ValueError):
                raise user_error('invalid_archive', f'Entrée illisible : {path}') from None
            if len(content) > cap:
                raise user_error('too_large', f'Contenu décompressé trop grand (dès {path}).')
            budget -= len(content)
            files[path] = content
    _check_unique(list(files))
    _check_totals([len(c) for c in files.values()], limits)
    return files


def extract_archive(data, destination, limits=None):
    """Extrait une archive validée dans un dossier vide qui vient d'être créé pour elle."""
    files = read_archive(data, limits)
    destination = Path(destination)
    if not destination.is_dir() or destination.is_symlink() or any(destination.iterdir()):
        raise ValueError('La destination doit être un dossier vide créé pour cette soumission.')
    root_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for path in sorted(files):
            *parents, name = path.split('/')
            directory_fd = os.dup(root_fd)
            try:
                for part in parents:  # jamais de résolution de chemin complet : pas de lien suivi
                    try:
                        os.mkdir(part, 0o755, dir_fd=directory_fd)
                    except FileExistsError:
                        pass
                    next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                    os.close(directory_fd)
                    directory_fd = next_fd
                file_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644,
                                  dir_fd=directory_fd)
                with os.fdopen(file_fd, 'wb') as handle:
                    handle.write(files[path])
            finally:
                os.close(directory_fd)
    finally:
        os.close(root_fd)
    return sorted(files)


def archive_digest(data):
    """Empreinte stable de l'archive, utilisable pour la déduplication."""
    return hashlib.sha256(data).hexdigest()
