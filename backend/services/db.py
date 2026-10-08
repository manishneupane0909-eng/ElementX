"""SQLite / SQLAlchemy session helpers for scientific persistence."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from models.research import Base

logger = logging.getLogger("elementx")

DEFAULT_DATABASE_URL = "sqlite:///./data/elementx.db"
DEFAULT_BUSY_TIMEOUT_MS = 10_000

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_initialized = False


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def busy_timeout_ms() -> int:
    """How long a writer waits for the SQLite lock before failing (milliseconds)."""
    raw = os.getenv("SQLITE_BUSY_TIMEOUT_MS", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_BUSY_TIMEOUT_MS
    except ValueError:
        return DEFAULT_BUSY_TIMEOUT_MS
    return value if value > 0 else DEFAULT_BUSY_TIMEOUT_MS


def _is_file_sqlite(url: str) -> bool:
    if not url.startswith("sqlite"):
        return False
    raw_path = url.split(":///", 1)[-1] if ":///" in url else ""
    return raw_path not in {"", ":memory:"} and not raw_path.startswith("file::memory")


def _install_sqlite_pragmas(engine: Engine, *, wal: bool) -> None:
    """Apply per-connection reliability settings to every new SQLite connection.

    * ``busy_timeout`` makes a blocked writer wait instead of failing immediately.
    * ``journal_mode=WAL`` lets readers proceed during a write and survives crashes
      without a rollback journal (file-backed databases only).
    * ``synchronous=NORMAL`` is the documented durable setting for WAL.
    """
    timeout_ms = busy_timeout_ms()

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout = {int(timeout_ms)}")
            if wal:
                mode = cursor.execute("PRAGMA journal_mode = WAL").fetchone()
                if not mode or str(mode[0]).lower() != "wal":
                    logger.warning("SQLite WAL mode could not be enabled (mode=%s)", mode)
                cursor.execute("PRAGMA synchronous = NORMAL")
        finally:
            cursor.close()


def sqlite_settings(engine: Engine) -> dict[str, object]:
    """Read back the effective SQLite settings (used by tests and diagnostics)."""
    with engine.connect() as connection:
        return {
            "journal_mode": connection.exec_driver_sql("PRAGMA journal_mode").scalar(),
            "busy_timeout": connection.exec_driver_sql("PRAGMA busy_timeout").scalar(),
            "synchronous": connection.exec_driver_sql("PRAGMA synchronous").scalar(),
        }


def storage_ready() -> bool:
    """True when the research database answers and the data directory is writable."""
    import tempfile

    from services.storage import get_data_dir

    try:
        with get_engine().connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        data_dir = get_data_dir()
        if not data_dir.is_dir():
            return False
        with tempfile.TemporaryFile(dir=data_dir):
            pass
        return True
    except Exception:  # noqa: BLE001 - health probe must never raise
        return False


def configure_engine(database_url: str | None = None) -> Engine:
    global _engine, _session_factory, _initialized
    url = database_url or get_database_url()
    is_sqlite = url.startswith("sqlite")
    connect_args: dict[str, object] = {}
    if is_sqlite:
        connect_args = {"check_same_thread": False, "timeout": busy_timeout_ms() / 1000}
    _ensure_sqlite_parent(url)
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, connect_args=connect_args)
    if is_sqlite:
        _install_sqlite_pragmas(_engine, wal=_is_file_sqlite(url))
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    _initialized = False
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        configure_engine()
    assert _engine is not None
    return _engine


OWNER_COLUMN = "owner_user_id"
OWNER_INDEX = "ix_scientific_samples_owner_user_id"


def upgrade_schema(engine: Engine) -> list[str]:
    """Apply additive, idempotent upgrades to databases created by earlier milestones.

    ``create_all`` creates missing tables but never alters existing ones, so columns
    added after a database was first created are added here. Existing rows are kept
    unchanged; no data is deleted or rewritten.
    """
    applied: list[str] = []
    inspector = inspect(engine)
    if "scientific_samples" not in inspector.get_table_names():
        return applied

    columns = {column["name"] for column in inspector.get_columns("scientific_samples")}
    with engine.begin() as connection:
        if OWNER_COLUMN not in columns:
            connection.execute(
                text(f"ALTER TABLE scientific_samples ADD COLUMN {OWNER_COLUMN} VARCHAR(128)")
            )
            applied.append(f"added scientific_samples.{OWNER_COLUMN}")
        existing_indexes = {
            index["name"] for index in inspect(connection).get_indexes("scientific_samples")
        }
        if OWNER_INDEX not in existing_indexes:
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {OWNER_INDEX} "
                    f"ON scientific_samples ({OWNER_COLUMN})"
                )
            )
            applied.append(f"created index {OWNER_INDEX}")
    return applied


def init_db() -> None:
    global _initialized
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    upgrade_schema(engine)
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


def get_db_session_factory_for_cli() -> sessionmaker[Session]:
    """Session factory for maintenance scripts (initialises and upgrades the schema)."""
    if not _initialized:
        init_db()
    return get_session_factory()


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
