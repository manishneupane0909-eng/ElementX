"""Filesystem storage for original scientific uploads."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import UUID

DEFAULT_DATA_DIR = "./data"
ALLOWED_ORIGINAL_SUFFIXES = {".dat", ".txt", ".csv", ".xy"}


def get_data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR))


def experiment_directory(experiment_id: str) -> Path:
    return get_data_dir() / "experiments" / _safe_experiment_id(experiment_id)


def write_original_file(experiment_id: str, content: bytes, suffix: str) -> str:
    """
    Write uploaded bytes to a generated directory as original.<suffix>.

    Returns a DATA_DIR-relative path. The original user filename is never used
    as a filesystem path.
    """
    normalized = _safe_suffix(suffix)
    safe_id = _safe_experiment_id(experiment_id)
    dest_dir = experiment_directory(safe_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"original{normalized}"
    dest.write_bytes(content)
    return f"experiments/{safe_id}/original{normalized}"


def write_original_dat(experiment_id: str, content: bytes) -> str:
    """Write magnetometry uploads as original.dat (existing path contract)."""
    return write_original_file(experiment_id, content, ".dat")


def resolve_stored_path(relative_path: str) -> Path:
    return get_data_dir() / relative_path


def remove_experiment_directory(experiment_id: str) -> None:
    directory = experiment_directory(experiment_id)
    if directory.exists():
        shutil.rmtree(directory)


def _safe_experiment_id(experiment_id: str) -> str:
    return str(UUID(experiment_id))


def _safe_suffix(suffix: str) -> str:
    normalized = suffix.lower()
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    if normalized not in ALLOWED_ORIGINAL_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_ORIGINAL_SUFFIXES))
        raise ValueError(f"Unsupported storage suffix {suffix!r}. Allowed: {allowed}.")
    return normalized
