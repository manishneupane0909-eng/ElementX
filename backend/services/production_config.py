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
    """The shared demo account is always available in dev, opt-in in production."""
    source = os.environ if env is None else env
    if not is_production(source):
        return True
    return source.get("ELEMENTX_ENABLE_DEMO", "").strip().lower() in {"1", "true", "yes"}


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


def _check_data_directory(env: Mapping[str, str], problems: list[str]) -> None:
    raw = env.get("DATA_DIR", "").strip()
    if not raw:
        problems.append("DATA_DIR is not set; production requires an explicit data directory.")
    else:
        path = Path(raw)
        if not path.is_absolute():
            problems.append("DATA_DIR must be an absolute path.")
        elif path.exists() and not path.is_dir():
            problems.append("DATA_DIR exists but is not a directory.")
        elif not _directory_is_writable(path):
            problems.append("DATA_DIR is not writable.")

    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        problems.append("DATABASE_URL is not set; production requires an explicit database.")
        return
    if database_url.startswith("sqlite:///"):
        raw_path = database_url.removeprefix("sqlite:///")
        if raw_path in {"", ":memory:"} or raw_path.startswith("file:"):
            problems.append("DATABASE_URL must point to a file-backed database in production.")
            return
        db_path = Path(raw_path)
        if not db_path.is_absolute():
            problems.append("DATABASE_URL sqlite path must be absolute.")
        elif not _directory_is_writable(db_path.parent):
            problems.append("DATABASE_URL sqlite directory is not writable.")


def _check_cors(env: Mapping[str, str], problems: list[str]) -> None:
    origins = parse_cors_origins(env.get("CORS_ORIGINS"))
    if not origins:
        problems.append("CORS_ORIGINS is not set; production requires an explicit origin list.")
    elif "*" in origins:
        problems.append("CORS_ORIGINS must not contain a wildcard in production.")


def validate_production_config(env: Optional[Mapping[str, str]] = None) -> list[str]:
    """Return a list of problems (empty when production config is acceptable)."""
    source = os.environ if env is None else env
    problems: list[str] = []
    _check_jwt_secret(source, problems)
    _check_identity_database(source, problems)
    _check_data_directory(source, problems)
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
