"""SQLite / SQLAlchemy session helpers for scientific persistence."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from models.research import Base

DEFAULT_DATABASE_URL = "sqlite:///./data/elementx.db"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_initialized = False


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def configure_engine(database_url: str | None = None) -> Engine:
    global _engine, _session_factory, _initialized
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _ensure_sqlite_parent(url)
    _engine = create_engine(url, connect_args=connect_args)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    _initialized = False
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        configure_engine()
    assert _engine is not None
    return _engine


def init_db() -> None:
    global _initialized
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _initialized = True


def reset_engine() -> None:
    global _engine, _session_factory, _initialized
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _initialized = False


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        configure_engine()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Iterator[Session]:
    if not _initialized:
        init_db()
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw_path = url.removeprefix("sqlite:///")
    if raw_path in {":memory:", ""} or raw_path.startswith("file:"):
        return
    parent = Path(raw_path).parent
    if str(parent) not in {"", "."}:
        parent.mkdir(parents=True, exist_ok=True)
