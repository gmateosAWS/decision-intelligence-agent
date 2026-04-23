"""
db/engine.py
------------
SQLAlchemy engine singleton.

The engine is created once per process from DATABASE_URL.  Callers that
need a session use ``get_session()``; callers that need the raw engine
(e.g. Alembic, raw DDL) use ``get_engine()``.

If DATABASE_URL is not set every function raises ``RuntimeError`` — the
callers are responsible for falling back to SQLite/FAISS in that case.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Start PostgreSQL and add DATABASE_URL to .env to use Postgres persistence."
        )
    return url


def get_engine() -> Engine:
    """Return (and lazily create) the singleton SQLAlchemy engine."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        url = _database_url()
        _engine = create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            future=True,
        )
        logger.info("SQLAlchemy engine created: %s", url.split("@")[-1])
    return _engine


def get_session_factory() -> sessionmaker:
    """Return (and lazily create) the session factory."""
    global _SessionLocal  # noqa: PLW0603
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autocommit=False, autoflush=False
        )
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager that yields a transactional SQLAlchemy session."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection() -> bool:
    """Return True if the database is reachable, False otherwise."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database connection check failed: %s", exc)
        return False
