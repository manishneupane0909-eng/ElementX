"""Back up, verify and restore ElementX research data (SQLite + original files).

Run from the ``backend`` directory with the same ``DATA_DIR`` / ``DATABASE_URL`` the
service uses (on Render: open a Shell on the service, where those are already set):

    python -m scripts.data_backup backup  [--dest DIR] [--keep N]
    python -m scripts.data_backup verify  ARCHIVE
    python -m scripts.data_backup restore ARCHIVE [--force]

``backup`` is safe to run while the service is live (SQLite online backup API).
``restore`` requires the service to be stopped and never deletes existing data.
See docs/BACKUP_AND_RECOVERY.md.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from services.data_backup import (
    BackupError,
    create_backup,
    prune_old_backups,
    restore_backup,
    sqlite_path_from_url,
    verify_backup,
)
from services.db import DEFAULT_DATABASE_URL
from services.storage import DEFAULT_DATA_DIR


def _paths(args: argparse.Namespace) -> tuple[Path, Path]:
    data_dir = Path(args.data_dir or os.getenv("DATA_DIR", DEFAULT_DATA_DIR))
    database_url = args.database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    return sqlite_path_from_url(database_url), data_dir


def _print_summary(summary: dict) -> None:
    print(
        f"  samples={summary['sample_count']} experiments={summary['experiment_count']} "
        f"original files={summary['file_count']}"
    )
    if summary["missing_referenced_files"]:
        print(f"  WARNING: {len(summary['missing_referenced_files'])} experiment(s) have no "
              "original file on disk:")
        for item in summary["missing_referenced_files"]:
            print(f"    - {item}")
    if summary["orphan_files"]:
        print(f"  note: {len(summary['orphan_files'])} original file(s) have no database row "
              "(harmless; included in the archive).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--data-dir", help="Override DATA_DIR")
    parser.add_argument("--database-url", help="Override DATABASE_URL (sqlite:/// only)")
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="Create a verified backup archive")
    backup.add_argument("--dest", help="Directory for the archive (default: <DATA_DIR>/backups)")
    backup.add_argument("--keep", type=int, help="Afterwards delete the oldest archives beyond N")

    verify = sub.add_parser("verify", help="Verify an archive without touching live data")
    verify.add_argument("archive")

    restore = sub.add_parser("restore", help="Restore database and original files together")
    restore.add_argument("archive")
    restore.add_argument("--force", action="store_true",
                         help="Allow restoring over existing data (it is moved aside, not deleted)")

    args = parser.parse_args(argv)
    try:
        database_path, data_dir = _paths(args)
        if args.command == "backup":
            dest = Path(args.dest) if args.dest else data_dir / "backups"
            report = create_backup(database_path, data_dir, dest)
            print(f"Backup written and verified: {report.archive}")
            _print_summary({
                "sample_count": report.sample_count,
                "experiment_count": report.experiment_count,
                "file_count": report.file_count,
                "missing_referenced_files": report.missing_referenced_files,
                "orphan_files": report.orphan_files,
            })
            if args.keep:
                for removed in prune_old_backups(dest, args.keep):
                    print(f"Pruned old backup: {removed.name}")
            print("Copy this file off the server (it contains private research data).")
            return 0 if report.complete else 2
        if args.command == "verify":
            summary = verify_backup(Path(args.archive))
            print("Archive verified (checksums, integrity_check, row/file consistency).")
            _print_summary(summary)
            return 0 if not summary["missing_referenced_files"] else 2
        summary = restore_backup(Path(args.archive), database_path, data_dir, force=args.force)
        print("Restore complete.")
        _print_summary(summary)
        if summary["previous_data_moved_to"]:
            print(f"  previous data preserved in: {summary['previous_data_moved_to']}")
        return 0
    except BackupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
