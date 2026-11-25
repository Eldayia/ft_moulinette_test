from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engines = {}


def engine_for(url):
    if url not in _engines:
        _engines[url] = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    return _engines[url]


def session_factory(url):
    return sessionmaker(engine_for(url), expire_on_commit=False)


@contextmanager
def transaction(factory):
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
