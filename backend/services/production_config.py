"""Production-only configuration guards.

Local development keeps its permissive defaults. When ``ELEMENTX_ENV=production``
the application refuses to start with unsafe settings. Error messages name the
offending variable and the reason only; configured values are never included.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Optional

PRODUCTION_ENV_NAME = "production"
INSECURE_DEFAULT_JWT_SECRET = "superlongrandomkey1234567890"
MIN_JWT_SECRET_LENGTH = 32

_INSECURE_SECRET_MARKERS = (
    "superlongrandomkey",
    "changeme",
    "change-me",
    "replace_me",
    "your_secret",
    "your-secret",
    "secret123",
)
_MONGO_PLACEHOLDERS = ("REPLACE_ME", "your_mongodb", "XXXXX", "<db_password>", "<password>")


class ProductionConfigError(RuntimeError):
    """Raised when production configuration is missing or unsafe."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        message = "Production configuration is invalid:\n" + "\n".join(
            f"  - {problem}" for problem in self.problems
        )
        super().__init__(message)


def is_production(env: Optional[Mapping[str, str]] = None) -> bool:
    source = os.environ if env is None else env
    return source.get("ELEMENTX_ENV", "").strip().lower() == PRODUCTION_ENV_NAME


def demo_bootstrap_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """The shared demo account bootstrap exists for local development only.

    It creates or resets a publicly documented login, so it is never available in
    production (there is deliberately no override).
    """
    source = os.environ if env is None else env
    return not is_production(source)


def api_docs_settings(env: Optional[Mapping[str, str]] = None) -> dict:
    """Interactive API docs and the OpenAPI schema are development tools only."""
    source = os.environ if env is None else env
    if is_production(source):
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


def parse_cors_origins(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


def cors_settings(env: Optional[Mapping[str, str]] = None) -> dict:
    """CORS arguments for ``CORSMiddleware``.

    Development keeps the permissive wildcard (the Vite dev server also uses a proxy).
    Production allows only the explicit ``CORS_ORIGINS`` list, never a wildcard.
    """
    source = os.environ if env is None else env
    if not is_production(source):
        return {
            "allow_origins": ["*"],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    origins = [o for o in parse_cors_origins(source.get("CORS_ORIGINS")) if o != "*"]
    return {
        "allow_origins": origins,
        "allow_credentials": False,
        "allow_methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
    }


def _check_jwt_secret(env: Mapping[str, str], problems: list[str]) -> None:
    secret = env.get("JWT_SECRET", "")
    if not secret.strip():
        problems.append("JWT_SECRET is not set.")
        return
    lowered = secret.lower()
    if secret == INSECURE_DEFAULT_JWT_SECRET or any(
        marker in lowered for marker in _INSECURE_SECRET_MARKERS
    ):
        problems.append("JWT_SECRET is a known insecure/placeholder value.")
    elif len(secret) < MIN_JWT_SECRET_LENGTH:
        problems.append(
            f"JWT_SECRET is too short (minimum {MIN_JWT_SECRET_LENGTH} characters)."
        )


def _check_identity_database(env: Mapping[str, str], problems: list[str]) -> None:
    uri = env.get("MONGODB_URI", "").strip()
    if not uri:
        problems.append(
            "MONGODB_URI is not set; production requires a persistent identity database."
        )
        return
    if any(marker in uri for marker in _MONGO_PLACEHOLDERS):
        problems.append("MONGODB_URI still contains a placeholder value.")
    elif not uri.startswith(("mongodb://", "mongodb+srv://")):
        problems.append("MONGODB_URI must start with mongodb:// or mongodb+srv://.")


def _directory_is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
        return True
    except OSError:
        return False


def _is_mount_point(path: Path) -> bool:
    return os.path.ismount(path)


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def _check_data_directory(env: Mapping[str, str], problems: list[str]) -> None:
    raw = env.get("DATA_DIR", "").strip()
    data_dir: Optional[Path] = None
    if not raw:
        problems.append("DATA_DIR is not set; production requires an explicit data directory.")
    else:
        path = Path(raw)
        if not path.is_absolute():
            problems.append("DATA_DIR must be an absolute path.")
        elif path.exists() and not path.is_dir():
            problems.append("DATA_DIR exists but is not a directory.")
        else:
            # A missing DATA_DIR is only acceptable when it can be created *on a mounted
            # volume*; otherwise production would silently write to ephemeral storage.
            if not path.exists() and not _truthy(env.get("ELEMENTX_ALLOW_UNMOUNTED_DATA_DIR", "")):
                problems.append(
                    "DATA_DIR does not exist. Attach the persistent disk at this path "
                    "(a missing mount would otherwise fall back to ephemeral storage)."
                )
            elif not _directory_is_writable(path):
                problems.append("DATA_DIR is not writable.")
            else:
                data_dir = path
                if not _is_mount_point(path) and not _truthy(
                    env.get("ELEMENTX_ALLOW_UNMOUNTED_DATA_DIR", "")
                ):
                    problems.append(
                        "DATA_DIR is not a mounted persistent volume; refusing to use "
                        "ephemeral storage in production. Attach a persistent disk at "
                        "DATA_DIR (set ELEMENTX_ALLOW_UNMOUNTED_DATA_DIR=true only for a "
                        "host whose directory is already durable)."
                    )

    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        problems.append("DATABASE_URL is not set; production requires an explicit database.")
        return
    if not database_url.startswith("sqlite:///"):
        problems.append("DATABASE_URL must be a sqlite:/// file database in production.")
        return
    raw_path = database_url.removeprefix("sqlite:///")
    if raw_path in {"", ":memory:"} or raw_path.startswith("file:"):
        problems.append("DATABASE_URL must point to a file-backed database in production.")
        return
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        problems.append("DATABASE_URL sqlite path must be absolute.")
        return
    if data_dir is None:
        return  # DATA_DIR problems already reported; do not create directories on guesswork.
    try:
        db_path.resolve().relative_to(data_dir.resolve())
    except ValueError:
        problems.append(
            "DATABASE_URL must live inside DATA_DIR so the database and the original "
            "scientific files share one persistent volume."
        )
        return
    if not _directory_is_writable(db_path.parent):
        problems.append("DATABASE_URL sqlite directory is not writable.")


def _check_single_instance(env: Mapping[str, str], problems: list[str]) -> None:
    """SQLite plus a local disk means exactly one process may write."""
    raw = env.get("WEB_CONCURRENCY", "").strip()
    if raw:
        try:
            workers = int(raw)
        except ValueError:
            problems.append("WEB_CONCURRENCY must be an integer (use 1).")
            return
        if workers != 1:
            problems.append(
                "WEB_CONCURRENCY must be 1: SQLite on a single persistent disk supports one "
                "worker process."
            )


def _check_cors(env: Mapping[str, str], problems: list[str]) -> None:
    origins = parse_cors_origins(env.get("CORS_ORIGINS"))
    if not origins:
        problems.append("CORS_ORIGINS is not set; production requires an explicit origin list.")
    elif "*" in origins:
        problems.append("CORS_ORIGINS must not contain a wildcard in production.")
    else:
        for origin in origins:
            if not origin.startswith(("https://", "http://")) or "/" in origin.split("://", 1)[1]:
                problems.append(
                    "CORS_ORIGINS entries must be bare origins like https://app.example.com."
                )
                break


def validate_production_config(env: Optional[Mapping[str, str]] = None) -> list[str]:
    """Return a list of problems (empty when production config is acceptable)."""
    source = os.environ if env is None else env
    problems: list[str] = []
    _check_jwt_secret(source, problems)
    _check_identity_database(source, problems)
    _check_data_directory(source, problems)
    _check_single_instance(source, problems)
    _check_cors(source, problems)
    return problems


def assert_production_ready(env: Optional[Mapping[str, str]] = None) -> None:
    """Raise ``ProductionConfigError`` when production is selected but unsafe."""
    source = os.environ if env is None else env
    if not is_production(source):
        return
    problems = validate_production_config(source)
    if problems:
        raise ProductionConfigError(problems)
