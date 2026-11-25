"""Interface commune des moteurs d'exécution."""
import abc
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .limits import Limits

PROJECTS = ('libft', 'printf')
SUBMISSION_ID = re.compile(r'^[0-9a-f]{32}$')

# Résultat global d'une soumission (AGENT.md §15), calculé par du code de confiance.
OUTCOMES = (
    'success', 'compilation_error', 'norm_error', 'test_failure', 'memory_error', 'timeout',
    'resource_limit', 'cancelled', 'infrastructure_error', 'sandbox_unavailable', 'unsupported',
)
# Résultats dus à l'infrastructure plutôt qu'au code soumis.
INFRASTRUCTURE_OUTCOMES = ('infrastructure_error', 'sandbox_unavailable')


class ExecutionError(Exception):
    """Erreur typée. category : « user » (requête ou fichiers refusés) ou « infrastructure »."""

    def __init__(self, category, code, message, retryable=False):
        if category not in ('user', 'infrastructure'):
            raise ValueError(category)
        super().__init__(message)
        self.category = category
        self.code = code
        self.message = message
        self.retryable = retryable

    def to_dict(self):
        return dict(category=self.category, code=self.code, message=self.message)


def user_error(code, message):
    return ExecutionError('user', code, message)


def infrastructure_error(code, message, retryable=False):
    return ExecutionError('infrastructure', code, message, retryable)


@dataclass(frozen=True)
class Options:
    norm: bool = True
    memory: bool = True
    build: bool = True
    iterations: int = 500
    seed: int = 42

    def __post_init__(self):
        for name in ('norm', 'memory', 'build'):
            if not isinstance(getattr(self, name), bool):
                raise user_error('invalid_options', f'« {name} » doit être un booléen.')
        if isinstance(self.iterations, bool) or not isinstance(self.iterations, int) or not 1 <= self.iterations <= 100_000:
            raise user_error('invalid_options', '« iterations » doit être un entier entre 1 et 100000.')
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed < 2 ** 32:
            raise user_error('invalid_options', '« seed » doit être un entier entre 0 et 2³²−1.')

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise user_error('invalid_options', '« options » doit être un objet.')
        unknown = set(data) - {'norm', 'memory', 'build', 'iterations', 'seed'}
        if unknown:
            raise user_error('invalid_options', 'Options inconnues : ' + ', '.join(sorted(unknown)))
        return cls(**data)

    def to_dict(self):
        return dict(norm=self.norm, memory=self.memory, build=self.build, iterations=self.iterations, seed=self.seed)


@dataclass
class Submission:
    """Une soumission. Exactement une source : archive ZIP validée, ou chemin local (moteurs locaux seuls)."""
    project: str
    archive: Optional[bytes] = None
    local_path: Optional[Path] = None
    options: Options = field(default_factory=Options)
    functions: tuple = ()
    #: mode fichier : chemin relatif d'un .c/.h de l'archive (ou du dossier local) à cibler
    target: Optional[str] = None
    tests_version: Optional[str] = None
    limits: Optional[Limits] = None
    submission_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self):
        if self.project not in PROJECTS:
            raise user_error('invalid_project', 'Projet attendu : libft ou printf.')
        if (self.archive is None) == (self.local_path is None):
            raise ValueError('Submission : indiquer archive ou local_path, pas les deux.')
        if not isinstance(self.submission_id, str) or not SUBMISSION_ID.match(self.submission_id):
            raise user_error('invalid_submission_id', 'Identifiant de soumission : 32 caractères hexadécimaux.')
        self.functions = tuple(self.functions)
        if self.local_path is not None:
            self.local_path = Path(self.local_path)


@dataclass
class ExecutionResult:
    submission_id: str
    outcome: str
    report: Optional[dict] = None
    metadata: dict = field(default_factory=dict)
    error: Optional[ExecutionError] = None

    def __post_init__(self):
        if self.outcome not in OUTCOMES:
            raise ValueError(f'outcome inconnu : {self.outcome}')

    @property
    def is_infrastructure_failure(self):
        return self.outcome in INFRASTRUCTURE_OUTCOMES

    def to_dict(self):
        return dict(submission_id=self.submission_id, outcome=self.outcome, report=self.report,
                    metadata=self.metadata, error=self.error.to_dict() if self.error else None)


@dataclass(frozen=True)
class Health:
    available: bool
    detail: str = ''


class ExecutionBackend(abc.ABC):
    """Contrat commun. execute() est synchrone : l'appelant (file, worker) gère la concurrence."""

    #: identifiant court, repris dans les métadonnées des rapports
    name = 'abstract'
    #: True seulement si le code soumis s'exécute dans un environnement isolé de l'hôte
    isolated = False

    @abc.abstractmethod
    def capabilities(self) -> dict:
        """Projets, analyseurs, options et limites pris en charge."""

    @abc.abstractmethod
    def check(self) -> Health:
        """Disponibilité du moteur, sans exécuter de soumission."""

    @abc.abstractmethod
    def execute(self, submission: Submission,
                on_event: Optional[Callable[[dict], None]] = None) -> ExecutionResult:
        """Exécute une soumission. Ne lève pas pour un échec de tests : il figure dans le résultat."""

    def cancel(self, submission_id: str) -> bool:
        """Demande l'annulation. True seulement si l'arrêt est effectif et confirmé."""
        return False
