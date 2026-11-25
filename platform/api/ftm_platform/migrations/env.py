"""Environnement Alembic : URL fournie par ftm_platform.manage (jamais lue d'un fichier versionné)."""
from alembic import context
from sqlalchemy import engine_from_config, pool

from ftm_platform.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section) or {}, prefix='sqlalchemy.',
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
