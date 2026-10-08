"""Bounded reading of uploaded files."""

from __future__ import annotations

import os

from fastapi import HTTPException, UploadFile

DEFAULT_MAX_UPLOAD_MB = 50
DEFAULT_MAX_CIF_UPLOAD_MB = 5
_CHUNK_BYTES = 1024 * 1024


def _limit_bytes(env_name: str, default_mb: int) -> int:
    raw = os.getenv(env_name, "").strip()
    try:
        megabytes = float(raw) if raw else float(default_mb)
    except ValueError:
        megabytes = float(default_mb)
    if megabytes <= 0:
        megabytes = float(default_mb)
    return int(megabytes * 1024 * 1024)


def max_upload_bytes() -> int:
    """Limit for measurement files (magnetometry / XRD)."""
    return _limit_bytes("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB)


def max_cif_upload_bytes() -> int:
    return _limit_bytes("MAX_CIF_UPLOAD_MB", DEFAULT_MAX_CIF_UPLOAD_MB)


def _describe_limit(limit_bytes: int) -> str:
    megabytes = limit_bytes / (1024 * 1024)
    return f"{megabytes:g} MB"


async def read_upload_limited(file: UploadFile, limit_bytes: int) -> bytes:
    """Read an upload fully, failing with HTTP 413 as soon as it exceeds the limit."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large. The maximum upload size is {_describe_limit(limit_bytes)}.",
            )
        chunks.append(chunk)
    return b"".join(chunks)
