"""Schéma PostgreSQL de la plateforme (SQLAlchemy 2). Les migrations Alembic en dérivent."""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Étapes affichées (AGENT.md §23), positionnées uniquement quand elles sont réellement atteintes.
STATUSES = ('queued', 'preparing', 'running', 'analyzing', 'done', 'failed')
FINISHED = ('done', 'failed')


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApiToken(Base):
    """Jeton personnel pour la CLI et les éditeurs ; seule son empreinte est stockée."""
    __tablename__ = 'api_tokens'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(64))
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Submission(Base):
    __tablename__ = 'submissions'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # = submission_id du protocole
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    project: Mapped[str] = mapped_column(String(16))
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    options: Mapped[dict] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(16))      # archive, files, pasted
    status: Mapped[str] = mapped_column(String(16), default='queued')
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    backend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    archive: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # effacée après exécution
    archive_sha256: Mapped[str] = mapped_column(String(64))
    archive_bytes: Mapped[int] = mapped_column(BigInteger)
    files_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index('ix_submissions_user_created', 'user_id', 'created_at'),
                      Index('ix_submissions_created', 'created_at'))
