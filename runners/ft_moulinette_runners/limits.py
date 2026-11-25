"""Limites configurables d'une soumission. Les valeurs par défaut sont celles de la mission (AGENT.md §12, §14)."""
import os
from dataclasses import asdict, dataclass, fields, replace

KIB = 1024
MIB = 1024 * KIB


@dataclass(frozen=True)
class Limits:
    # Fichiers (§12)
    max_upload_bytes: int = 5 * MIB
    max_uncompressed_bytes: int = 20 * MIB
    max_files: int = 200
    max_file_bytes: int = 2 * MIB
    max_path_length: int = 255
    max_path_depth: int = 16
    max_log_bytes: int = 256 * KIB
    max_report_bytes: int = 1 * MIB
    # Délais en secondes (§14). Le moteur applique un seul délai par commande :
    # command_timeout couvre compilation, exécution des bancs et Valgrind.
    command_timeout: int = 15
    submission_timeout: int = 60
    request_timeout: int = 120

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f'Limite invalide : {field.name}={value!r}')
        if self.max_file_bytes > self.max_uncompressed_bytes:
            raise ValueError('max_file_bytes ne peut pas dépasser max_uncompressed_bytes')
        if self.command_timeout > self.submission_timeout:
            raise ValueError('command_timeout ne peut pas dépasser submission_timeout')
        if self.submission_timeout >= self.request_timeout:
            raise ValueError('submission_timeout doit rester inférieur à request_timeout')

    def to_dict(self):
        return asdict(self)

    def narrowed(self, requested):
        """Limites demandées par l'appelant, sans jamais dépasser les maxima de ce service."""
        if not requested:
            return self
        if not isinstance(requested, dict):
            raise ValueError('limits doit être un objet')
        known = {field.name for field in fields(self)}
        unknown = set(requested) - known
        if unknown:
            raise ValueError('Limites inconnues : ' + ', '.join(sorted(unknown)))
        values = {}
        for name, value in requested.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f'Limite invalide : {name}={value!r}')
            values[name] = min(value, getattr(self, name))
        return replace(self, **values)

    @classmethod
    def from_env(cls, environ=None, prefix='FTM_LIMIT_'):
        """Lit FTM_LIMIT_MAX_FILES=…, etc. Une valeur illisible est une erreur, jamais ignorée."""
        environ = os.environ if environ is None else environ
        values = {}
        for field in fields(cls):
            raw = environ.get(prefix + field.name.upper())
            if raw is None or raw == '':
                continue
            try:
                values[field.name] = int(raw)
            except ValueError:
                raise ValueError(f'{prefix + field.name.upper()} doit être un entier') from None
        return cls(**values)
