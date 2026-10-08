"""Consistent backup and restore of ElementX research data.

A complete backup needs *both* halves of the scientific record:

* the SQLite database (samples, experiments, stored analysis JSON), and
* the original uploaded files under ``DATA_DIR/experiments/<uuid>/original.<ext>``.

The database is captured with SQLite's online backup API (``sqlite3.Connection.backup``),
which yields a transactionally consistent snapshot even while the application is writing
in WAL mode. Copying the ``.db`` file directly is *not* safe: committed data may still sit
in the ``-wal`` file, and a copy taken mid-write can be torn.

Ordering matters. The application writes an original file *before* committing its database
row. Snapshotting the database first and copying files second therefore guarantees every
row in the snapshot has its file present; at worst a file uploaded in between is archived
without a row (reported as an orphan, harmless).

Archive layout (``elementx-backup-<UTC timestamp>.tar.gz``)::

    manifest.json
    elementx.db                        # single-file snapshot (journal_mode=DELETE)
    experiments/<uuid>/original.<ext>  # byte-for-byte original uploads

Nothing here ever deletes scientific data. Restoring over existing data moves the old
database and files aside into ``restore-previous-<timestamp>/`` instead of removing them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BACKUP_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
DB_ARCHIVE_NAME = "elementx.db"
EXPERIMENTS_DIR = "experiments"
BACKUP_FILE_PREFIX = "elementx-backup-"
BACKUP_FILE_SUFFIX = ".tar.gz"
_BACKUP_NAME_RE = re.compile(r"^elementx-backup-\d{8}T\d{12}Z\.tar\.gz$")
_ORIGINAL_MEMBER_RE = re.compile(
    r"^experiments/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"/original\.[A-Za-z0-9]{1,8}$"
)
_PREVIOUS_PREFIX = "restore-previous-"


class BackupError(RuntimeError):
    """The backup/restore could not be completed safely."""


@dataclass
class BackupReport:
    archive: Path
    created_at: str
    sample_count: int
    experiment_count: int
    file_count: int
    total_bytes: int
    missing_referenced_files: list[str] = field(default_factory=list)
    orphan_files: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing_referenced_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise BackupError("Backups support sqlite:/// database URLs only.")
    raw = database_url.removeprefix("sqlite:///")
    if raw in {"", ":memory:"} or raw.startswith("file:"):
        raise BackupError("DATABASE_URL must point to a file-backed SQLite database.")
    return Path(raw)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_stamp(now: Optional[datetime] = None) -> str:
    # Microsecond resolution keeps names unique and lexicographically sortable.
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")


def _integrity_ok(connection: sqlite3.Connection) -> bool:
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    return len(rows) == 1 and str(rows[0][0]).lower() == "ok"


def _read_rows(db_file: Path) -> tuple[int, list[tuple[str, str]]]:
    """Return (sample_count, [(experiment_id, raw_file_path), ...]) from a snapshot."""
    connection = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        samples = connection.execute("SELECT COUNT(*) FROM scientific_samples").fetchone()[0]
        experiments = connection.execute(
            "SELECT id, raw_file_path FROM scientific_experiments ORDER BY id"
        ).fetchall()
        return int(samples), [(str(i), str(p)) for i, p in experiments]
    finally:
        connection.close()


def _safe_relative(raw: str) -> str:
    """Normalise a DB ``raw_file_path`` and reject anything that could escape DATA_DIR."""
    normalized = raw.replace("\\", "/")
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise BackupError(f"Unsafe raw_file_path in database: {raw!r}")
    return "/".join(parts)


def _snapshot_database(source: Path, destination: Path) -> None:
    """Consistent online snapshot using SQLite's backup API (never a file copy)."""
    if not source.is_file():
        raise BackupError("The SQLite database file does not exist; nothing to back up.")
    src = sqlite3.connect(str(source), timeout=30)
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
            # Make the snapshot a single self-contained file (no -wal/-shm companions).
            dst.execute("PRAGMA journal_mode = DELETE")
            if not _integrity_ok(dst):
                raise BackupError("Snapshot failed SQLite integrity_check; backup aborted.")
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def create_backup(
    database_path: Path,
    data_dir: Path,
    destination_dir: Path,
    *,
    now: Optional[datetime] = None,
) -> BackupReport:
    """Create ``elementx-backup-<UTC>.tar.gz`` in ``destination_dir`` and verify it."""
    database_path = Path(database_path)
    data_dir = Path(data_dir)
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)

    created_at = (now or datetime.now(timezone.utc)).isoformat()
    archive_path = destination_dir / f"{BACKUP_FILE_PREFIX}{_utc_stamp(now)}{BACKUP_FILE_SUFFIX}"
    if archive_path.exists():
        raise BackupError(f"Refusing to overwrite existing backup {archive_path.name}.")

    with tempfile.TemporaryDirectory(prefix="elementx-backup-", dir=destination_dir) as work:
        work_dir = Path(work)
        snapshot = work_dir / DB_ARCHIVE_NAME

        # 1. Database first (see module docstring for why the order matters).
        _snapshot_database(database_path, snapshot)
        sample_count, experiment_rows = _read_rows(snapshot)

        # 2. Original files second.
        experiments_root = data_dir / EXPERIMENTS_DIR
        files: dict[str, dict] = {}
        if experiments_root.is_dir():
            for path in sorted(p for p in experiments_root.rglob("*") if p.is_file()):
                relative = path.relative_to(data_dir).as_posix()
                if not _ORIGINAL_MEMBER_RE.match(relative):
                    continue  # only archive files that follow the storage contract
                files[relative] = {"size": path.stat().st_size, "sha256": _sha256(path)}

        referenced = {_safe_relative(path) for _, path in experiment_rows}
        missing = sorted(referenced - set(files))
        orphans = sorted(set(files) - referenced)

        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": created_at,
            "database": {
                "file": DB_ARCHIVE_NAME,
                "sha256": _sha256(snapshot),
                "sample_count": sample_count,
                "experiment_count": len(experiment_rows),
            },
            "files": files,
            "missing_referenced_files": missing,
            "orphan_files": orphans,
        }
        manifest_path = work_dir / MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        partial = archive_path.with_name(archive_path.name + ".partial")
        try:
            with tarfile.open(partial, "w:gz") as tar:
                tar.add(manifest_path, arcname=MANIFEST_NAME)
                tar.add(snapshot, arcname=DB_ARCHIVE_NAME)
                for relative in files:
                    tar.add(data_dir / relative, arcname=relative)
            with partial.open("rb") as handle:
                os.fsync(handle.fileno())
            os.chmod(partial, 0o600)
            os.replace(partial, archive_path)
        finally:
            if partial.exists():
                partial.unlink()

    # 3. Prove the archive we just wrote is restorable.
    verify_backup(archive_path)

    return BackupReport(
        archive=archive_path,
        created_at=created_at,
        sample_count=sample_count,
        experiment_count=len(experiment_rows),
        file_count=len(files),
        total_bytes=sum(entry["size"] for entry in files.values()),
        missing_referenced_files=missing,
        orphan_files=orphans,
    )


def prune_old_backups(destination_dir: Path, keep: int) -> list[Path]:
    """Delete the oldest ``elementx-backup-*.tar.gz`` archives beyond ``keep`` (opt-in)."""
    if keep < 1:
        raise BackupError("--keep must be at least 1.")
    archives = sorted(p for p in Path(destination_dir).iterdir() if _BACKUP_NAME_RE.match(p.name))
    removed = archives[:-keep] if len(archives) > keep else []
    for path in removed:
        path.unlink()
    return removed


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def _validate_member(member: tarfile.TarInfo) -> None:
    name = member.name
    if not member.isfile():
        raise BackupError(f"Archive contains a non-regular entry: {name!r}.")
    if name in {MANIFEST_NAME, DB_ARCHIVE_NAME}:
        return
    if not _ORIGINAL_MEMBER_RE.match(name):
        raise BackupError(f"Archive contains an unexpected path: {name!r}.")


def _extract_archive(archive: Path, destination: Path) -> dict:
    """Safely extract an archive (regular files with whitelisted names only)."""
    if not tarfile.is_tarfile(archive):
        raise BackupError("The file is not a valid ElementX backup archive.")
    try:
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                _validate_member(member)
            names = {m.name for m in members}
            if MANIFEST_NAME not in names or DB_ARCHIVE_NAME not in names:
                raise BackupError("Backup archive is missing its manifest or database snapshot.")
            for member in members:
                target = destination / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                assert source is not None
                with target.open("wb") as out:
                    shutil.copyfileobj(source, out)
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise BackupError("The backup archive is unreadable or corrupt.") from exc
    return json.loads((destination / MANIFEST_NAME).read_text(encoding="utf-8"))


def _verify_extracted(root: Path, manifest: dict) -> dict:
    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupError("Unsupported backup format version.")

    db_file = root / DB_ARCHIVE_NAME
    if _sha256(db_file) != manifest["database"]["sha256"]:
        raise BackupError("Database snapshot checksum mismatch; the backup is corrupt.")

    connection = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        if not _integrity_ok(connection):
            raise BackupError("Database snapshot failed SQLite integrity_check.")
    finally:
        connection.close()

    for relative, entry in manifest["files"].items():
        path = root / relative
        if not path.is_file():
            raise BackupError(f"Archive is missing {relative}.")
        if _sha256(path) != entry["sha256"] or path.stat().st_size != entry["size"]:
            raise BackupError(f"Checksum mismatch for {relative}; the backup is corrupt.")

    extracted = {
        p.relative_to(root).as_posix() for p in (root / EXPERIMENTS_DIR).rglob("*") if p.is_file()
    } if (root / EXPERIMENTS_DIR).exists() else set()
    if extracted != set(manifest["files"]):
        raise BackupError("Archive contents do not match the manifest.")

    samples, experiment_rows = _read_rows(db_file)
    if samples != manifest["database"]["sample_count"] or len(experiment_rows) != manifest[
        "database"
    ]["experiment_count"]:
        raise BackupError("Row counts do not match the manifest.")

    missing = sorted({_safe_relative(p) for _, p in experiment_rows} - set(manifest["files"]))
    return {
        "created_at": manifest["created_at"],
        "sample_count": samples,
        "experiment_count": len(experiment_rows),
        "file_count": len(manifest["files"]),
        "missing_referenced_files": missing,
        "orphan_files": list(manifest.get("orphan_files", [])),
    }


def verify_backup(archive: Path) -> dict:
    """Check an archive end to end without touching any live data."""
    with tempfile.TemporaryDirectory(prefix="elementx-verify-") as work:
        root = Path(work)
        manifest = _extract_archive(Path(archive), root)
        return _verify_extracted(root, manifest)


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def _target_has_data(database_path: Path, data_dir: Path) -> bool:
    experiments = data_dir / EXPERIMENTS_DIR
    return database_path.exists() or (experiments.exists() and any(experiments.iterdir()))


def restore_backup(
    archive: Path,
    database_path: Path,
    data_dir: Path,
    *,
    force: bool = False,
    now: Optional[datetime] = None,
) -> dict:
    """Restore the database *and* original files from ``archive`` together.

    The application must be stopped first. Existing data is never deleted: with
    ``force=True`` the current database (plus ``-wal``/``-shm``) and ``experiments/`` are
    moved into ``<DATA_DIR>/restore-previous-<UTC>/``.
    """
    database_path = Path(database_path)
    data_dir = Path(data_dir)
    stamp = _utc_stamp(now)
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    if _target_has_data(database_path, data_dir) and not force:
        raise BackupError(
            "The target already contains data. Stop the application and re-run with --force; "
            "existing data will be moved aside, not deleted."
        )

    staging = Path(tempfile.mkdtemp(prefix=".restore-staging-", dir=data_dir))
    try:
        manifest = _extract_archive(Path(archive), staging)
        summary = _verify_extracted(staging, manifest)

        previous_dir: Optional[Path] = None
        if _target_has_data(database_path, data_dir):
            previous_dir = data_dir / f"{_PREVIOUS_PREFIX}{stamp}"
            suffix = 1
            while previous_dir.exists():
                previous_dir = data_dir / f"{_PREVIOUS_PREFIX}{stamp}-{suffix}"
                suffix += 1
            previous_dir.mkdir(parents=True)
            for companion in ("", "-wal", "-shm"):
                existing = database_path.with_name(database_path.name + companion)
                if existing.exists():
                    shutil.move(str(existing), str(previous_dir / existing.name))
            experiments = data_dir / EXPERIMENTS_DIR
            if experiments.exists():
                shutil.move(str(experiments), str(previous_dir / EXPERIMENTS_DIR))

        # Same filesystem as the target (staging lives inside DATA_DIR) -> atomic renames.
        staged_experiments = staging / EXPERIMENTS_DIR
        if staged_experiments.exists():
            os.replace(staged_experiments, data_dir / EXPERIMENTS_DIR)
        else:
            (data_dir / EXPERIMENTS_DIR).mkdir(exist_ok=True)
        pending_db = database_path.with_name(database_path.name + ".restoring")
        shutil.copyfile(staging / DB_ARCHIVE_NAME, pending_db)
        os.chmod(pending_db, 0o600)
        os.replace(pending_db, database_path)

        connection = sqlite3.connect(str(database_path))
        try:
            if not _integrity_ok(connection):
                raise BackupError("Restored database failed integrity_check.")
        finally:
            connection.close()
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    summary["previous_data_moved_to"] = str(previous_dir) if previous_dir else None
    return summary
