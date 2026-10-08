"""Backup/restore of the SQLite database and original scientific files together."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from scripts import data_backup as cli
from services.data_backup import (
    BackupError,
    create_backup,
    prune_old_backups,
    restore_backup,
    sqlite_path_from_url,
    verify_backup,
)
from services.db import configure_engine, get_db, get_session_factory, init_db, reset_engine
from tests.auth_helpers import USER_A_ID, auth_headers
from tests.research_base import ResearchApiTestCase


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    base = root / "experiments"
    if not base.exists():
        return {}
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(base.rglob("*")) if p.is_file()}


class BackupRestoreTests(ResearchApiTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        sample = cls.create_sample_static("Backup sample")
        cls.sample_id = sample["id"]
        mag = cls.client_a.post(
            f"/api/research/samples/{cls.sample_id}/experiments",
            files={"file": ("Fe2CoGe.dat", cls.magnetometry_bytes)},
        )
        xrd = cls.client_a.post(
            f"/api/research/samples/{cls.sample_id}/xrd-experiments",
            files={"file": ("pattern.xy", cls.xrd_bytes)},
        )
        assert mag.status_code == 201 and xrd.status_code == 201, (mag.text, xrd.text)
        cls.mag = mag.json()
        cls.xrd = xrd.json()

    @classmethod
    def create_sample_static(cls, name: str) -> dict:
        response = cls.client_a.post(
            "/api/research/samples", json={"name": name, "formula": "Fe2CoGe", "notes": None}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def setUp(self) -> None:
        self._work = tempfile.TemporaryDirectory()
        self.work = Path(self._work.name)
        self.backups = self.work / "backups"

    def tearDown(self) -> None:
        self._work.cleanup()

    # -- backup ---------------------------------------------------------------------

    def test_backup_contains_database_and_original_files_and_verifies(self) -> None:
        report = create_backup(self.db_path, self.data_dir, self.backups)
        self.assertTrue(report.archive.exists())
        self.assertTrue(report.complete)
        self.assertEqual(report.file_count, len(tree_hashes(self.data_dir)))
        self.assertGreaterEqual(report.experiment_count, 2)
        with tarfile.open(report.archive) as tar:
            names = tar.getnames()
        self.assertIn("manifest.json", names)
        self.assertIn("elementx.db", names)
        self.assertTrue(any(n.endswith("/original.dat") for n in names))
        self.assertTrue(any(n.endswith("/original.xy") for n in names))
        self.assertEqual(oct(report.archive.stat().st_mode & 0o777), "0o600")
        self.assertEqual(verify_backup(report.archive)["missing_referenced_files"], [])

    def test_backup_uses_sqlite_backup_api_not_a_raw_file_copy(self) -> None:
        """Committed rows still sitting in the -wal file must be in the backup."""
        marker = self.create_sample(name="WAL-only sample")
        db_copy_only = self.work / "naive-copy.db"
        shutil.copyfile(self.db_path, db_copy_only)  # what an unsafe copy would capture
        with sqlite3.connect(db_copy_only) as naive:
            try:
                naive_names = {r[0] for r in naive.execute("SELECT name FROM scientific_samples")}
            except sqlite3.OperationalError:
                naive_names = set()  # an unsafe copy can even miss whole tables

        report = create_backup(self.db_path, self.data_dir, self.backups)
        restored = self.work / "restored"
        restore_backup(report.archive, restored / "elementx.db", restored)
        with sqlite3.connect(restored / "elementx.db") as good:
            good_names = {r[0] for r in good.execute("SELECT name FROM scientific_samples")}

        self.assertIn(marker["name"], good_names)
        self.assertTrue(
            good_names >= naive_names,
            "the backup must never contain less than a raw copy",
        )

    def test_backup_while_the_service_is_writing_is_consistent(self) -> None:
        sample = self.create_sample(name="Busy sample")
        errors: list[Exception] = []
        stop = threading.Event()

        def writer() -> None:
            try:
                while not stop.is_set():
                    self.upload_xrd(sample["id"])
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            reports = [create_backup(self.db_path, self.data_dir, self.backups) for _ in range(3)]
        finally:
            stop.set()
            thread.join(timeout=30)
        self.assertEqual(errors, [])
        for report in reports:
            summary = verify_backup(report.archive)
            # Every row in the snapshot has its original file (files are written before commit).
            self.assertEqual(summary["missing_referenced_files"], [])

    def test_backup_never_modifies_or_removes_live_data(self) -> None:
        before = tree_hashes(self.data_dir)
        create_backup(self.db_path, self.data_dir, self.backups)
        self.assertEqual(before, tree_hashes(self.data_dir))
        self.assertTrue(self.db_path.exists())

    def test_missing_original_file_is_reported_not_hidden(self) -> None:
        victim = self.data_dir / self.mag["rawFilePath"] if "rawFilePath" in self.mag else None
        with sqlite3.connect(self.db_path) as connection:
            relative = connection.execute(
                "SELECT raw_file_path FROM scientific_experiments WHERE id = ?", (self.mag["id"],)
            ).fetchone()[0]
        victim = self.data_dir / relative
        hidden = victim.with_name("original.dat.hidden")
        victim.rename(hidden)
        try:
            report = create_backup(self.db_path, self.data_dir, self.backups)
            self.assertFalse(report.complete)
            self.assertIn(relative, report.missing_referenced_files)
        finally:
            hidden.rename(victim)

    # -- restore --------------------------------------------------------------------

    def test_restore_into_fresh_location_recovers_metadata_and_raw_files_together(self) -> None:
        report = create_backup(self.db_path, self.data_dir, self.backups)
        original_files = tree_hashes(self.data_dir)

        target = self.work / "new-volume"
        db_target = target / "elementx.db"
        summary = restore_backup(report.archive, db_target, target)

        self.assertEqual(summary["previous_data_moved_to"], None)
        self.assertEqual(tree_hashes(target), {k: v for k, v in original_files.items()})
        with sqlite3.connect(db_target) as a, sqlite3.connect(self.db_path) as b:
            query = "SELECT id, sample_id, raw_file_path, analysis_version, analysis_json FROM scientific_experiments ORDER BY id"
            self.assertEqual(a.execute(query).fetchall(), b.execute(query).fetchall())
            query = "SELECT id, name, formula, owner_user_id FROM scientific_samples ORDER BY id"
            self.assertEqual(a.execute(query).fetchall(), b.execute(query).fetchall())

    def test_restored_service_serves_identical_scientific_results(self) -> None:
        mag_before = self.client_a.get(f"/api/research/experiments/{self.mag['id']}").json()
        xrd_before = self.client_a.get(f"/api/research/experiments/{self.xrd['id']}").json()
        report = create_backup(self.db_path, self.data_dir, self.backups)

        target = self.work / "disaster-recovery"
        restore_backup(report.archive, target / "elementx.db", target)

        previous = {k: os.environ.get(k) for k in ("DATABASE_URL", "DATA_DIR")}
        try:
            os.environ["DATABASE_URL"] = f"sqlite:///{target / 'elementx.db'}"
            os.environ["DATA_DIR"] = str(target)
            self.restart_engine()
            mag_after = self.client_a.get(f"/api/research/experiments/{self.mag['id']}").json()
            xrd_after = self.client_a.get(f"/api/research/experiments/{self.xrd['id']}").json()
            self.assertEqual(mag_after, mag_before)
            self.assertEqual(xrd_after, xrd_before)
            # Ownership survives: another account still cannot see the restored records.
            other = TestClient(app, headers=auth_headers("someone-else"))
            self.assertEqual(other.get(f"/api/research/experiments/{self.mag['id']}").status_code, 404)
            # The restored volume keeps accepting new uploads.
            sample = self.create_sample(name="After restore")
            self.assertEqual(self.upload_magnetometry(sample["id"]).status_code, 201)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            self.restart_engine()

    def test_restore_refuses_to_overwrite_existing_data_without_force(self) -> None:
        report = create_backup(self.db_path, self.data_dir, self.backups)
        before = tree_hashes(self.data_dir)
        with self.assertRaises(BackupError):
            restore_backup(report.archive, self.db_path, self.data_dir)
        self.assertEqual(before, tree_hashes(self.data_dir))

    def test_forced_restore_moves_existing_data_aside_instead_of_deleting_it(self) -> None:
        target = self.work / "target"
        target.mkdir()
        old_db = target / "elementx.db"
        with sqlite3.connect(old_db) as connection:
            connection.execute("CREATE TABLE precious (x TEXT)")
            connection.execute("INSERT INTO precious VALUES ('keep me')")
        (target / "experiments" / "11111111-1111-1111-1111-111111111111").mkdir(parents=True)
        precious_file = target / "experiments" / "11111111-1111-1111-1111-111111111111" / "original.dat"
        precious_file.write_bytes(b"old scientific bytes")

        report = create_backup(self.db_path, self.data_dir, self.backups)
        summary = restore_backup(report.archive, old_db, target, force=True)

        moved = Path(summary["previous_data_moved_to"])
        self.assertTrue(moved.is_dir())
        with sqlite3.connect(moved / "elementx.db") as connection:
            self.assertEqual(connection.execute("SELECT x FROM precious").fetchone()[0], "keep me")
        self.assertEqual(
            (moved / "experiments" / "11111111-1111-1111-1111-111111111111" / "original.dat").read_bytes(),
            b"old scientific bytes",
        )
        self.assertEqual(tree_hashes(target), tree_hashes(self.data_dir))

    # -- integrity ------------------------------------------------------------------

    def _rewrite_archive(self, source: Path, mutate) -> Path:
        out = self.work / "tampered.tar.gz"
        with tarfile.open(source) as tin, tarfile.open(out, "w:gz") as tout:
            for member in tin.getmembers():
                data = tin.extractfile(member).read()
                result = mutate(member.name, data)
                if result is None:
                    continue
                name, payload = result
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                tout.addfile(info, io.BytesIO(payload))
        return out

    def test_corrupted_original_file_is_detected(self) -> None:
        report = create_backup(self.db_path, self.data_dir, self.backups)

        def corrupt(name: str, data: bytes):
            if name.endswith("original.dat"):
                data = data[:-1] + bytes([data[-1] ^ 0xFF])
            return name, data

        bad = self._rewrite_archive(report.archive, corrupt)
        with self.assertRaisesRegex(BackupError, "Checksum mismatch"):
            verify_backup(bad)
        with self.assertRaises(BackupError):
            restore_backup(bad, self.work / "x" / "elementx.db", self.work / "x")
        self.assertFalse((self.work / "x" / "elementx.db").exists())

    def test_corrupted_database_snapshot_is_detected(self) -> None:
        report = create_backup(self.db_path, self.data_dir, self.backups)

        def corrupt(name: str, data: bytes):
            if name == "elementx.db":
                middle = len(data) // 2
                data = data[:middle] + bytes([data[middle] ^ 0xFF]) + data[middle + 1 :]
            return name, data

        with self.assertRaises(BackupError):
            verify_backup(self._rewrite_archive(report.archive, corrupt))

    def test_archive_with_path_traversal_is_rejected(self) -> None:
        evil_archive = self.work / "evil.tar.gz"
        with tarfile.open(evil_archive, "w:gz") as tar:
            info = tarfile.TarInfo("../../escape.txt")
            info.size = 5
            tar.addfile(info, io.BytesIO(b"pwned"))
        with self.assertRaisesRegex(BackupError, "unexpected path"):
            verify_backup(evil_archive)
        self.assertFalse((self.work.parent / "escape.txt").exists())

    def test_non_archive_input_is_rejected(self) -> None:
        junk = self.work / "junk.tar.gz"
        junk.write_bytes(b"not an archive")
        with self.assertRaises(BackupError):
            verify_backup(junk)

    # -- retention and CLI ----------------------------------------------------------

    def test_prune_only_touches_backup_archives_and_only_when_asked(self) -> None:
        self.backups.mkdir()
        stamps = ["20260101T000000000000Z", "20260102T000000000000Z", "20260103T000000000000Z"]
        for stamp in stamps:
            (self.backups / f"elementx-backup-{stamp}.tar.gz").write_bytes(b"x")
        keepsake = self.backups / "notes.txt"
        keepsake.write_text("mine")
        removed = prune_old_backups(self.backups, keep=2)
        self.assertEqual([p.name for p in removed], ["elementx-backup-20260101T000000000000Z.tar.gz"])
        self.assertTrue(keepsake.exists())
        with self.assertRaises(BackupError):
            prune_old_backups(self.backups, keep=0)

    def test_backups_are_not_overwritten(self) -> None:
        moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
        create_backup(self.db_path, self.data_dir, self.backups, now=moment)
        with self.assertRaises(BackupError):
            create_backup(self.db_path, self.data_dir, self.backups, now=moment)

    def test_cli_backup_verify_restore_round_trip(self) -> None:
        argv_base = ["--data-dir", str(self.data_dir), "--database-url", f"sqlite:///{self.db_path}"]
        self.assertEqual(cli.main([*argv_base, "backup", "--dest", str(self.backups)]), 0)
        archive = next(self.backups.glob("elementx-backup-*.tar.gz"))
        self.assertEqual(cli.main(["verify", str(archive)]), 0)

        target = self.work / "cli-target"
        restore_argv = ["--data-dir", str(target), "--database-url", f"sqlite:///{target / 'elementx.db'}"]
        self.assertEqual(cli.main([*restore_argv, "restore", str(archive)]), 0)
        self.assertEqual(tree_hashes(target), tree_hashes(self.data_dir))
        # Second restore over existing data needs --force.
        self.assertEqual(cli.main([*restore_argv, "restore", str(archive)]), 1)
        self.assertEqual(cli.main([*restore_argv, "restore", str(archive), "--force"]), 0)

    def test_sqlite_path_from_url_rejects_non_file_databases(self) -> None:
        for url in ("postgresql://x/y", "sqlite:///:memory:", "sqlite://"):
            with self.assertRaises(BackupError):
                sqlite_path_from_url(url)


class BackupOfLegacyDatabaseTests(unittest.TestCase):
    """A backup of a pre-5A database (no owner column) must restore and upgrade cleanly."""

    def test_legacy_schema_round_trips_and_is_upgraded_on_next_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            db_path = data / "elementx.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE scientific_samples (
                    id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL, formula VARCHAR(255),
                    notes TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
                CREATE TABLE scientific_experiments (
                    id VARCHAR(36) PRIMARY KEY, sample_id VARCHAR(36) NOT NULL,
                    experiment_type VARCHAR(64) NOT NULL, original_filename VARCHAR(512) NOT NULL,
                    uploaded_at DATETIME NOT NULL, raw_file_path VARCHAR(1024) NOT NULL,
                    analysis_version VARCHAR(32) NOT NULL, analysis_json JSON NOT NULL,
                    user_confirmed_mass_mg FLOAT);
                INSERT INTO scientific_samples VALUES
                  ('21280b0c-154c-41f5-9b91-b7bf11255017','Legacy','Fe',NULL,'2026-01-01','2026-01-01');
                INSERT INTO scientific_experiments VALUES
                  ('12db3385-8276-4687-ae63-737c91086de3','21280b0c-154c-41f5-9b91-b7bf11255017',
                   'magnetometry','a.dat','2026-01-01',
                   'experiments/12db3385-8276-4687-ae63-737c91086de3/original.dat','v',
                   '{"k": 1}', NULL);
                """
            )
            connection.commit()
            connection.close()
            raw = data / "experiments" / "12db3385-8276-4687-ae63-737c91086de3"
            raw.mkdir(parents=True)
            (raw / "original.dat").write_bytes(b"legacy bytes")

            report = create_backup(db_path, data, root / "backups")
            restored = root / "restored"
            restore_backup(report.archive, restored / "elementx.db", restored)

            previous = os.environ.get("DATABASE_URL")
            try:
                engine = configure_engine(f"sqlite:///{restored / 'elementx.db'}")
                init_db()
                with engine.connect() as conn:
                    columns = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(scientific_samples)")}
                    count = conn.exec_driver_sql("SELECT COUNT(*) FROM scientific_experiments").scalar()
                self.assertIn("owner_user_id", columns)
                self.assertEqual(count, 1)
            finally:
                reset_engine()
                if previous is not None:
                    os.environ["DATABASE_URL"] = previous
            self.assertEqual(
                (restored / "experiments" / "12db3385-8276-4687-ae63-737c91086de3" / "original.dat").read_bytes(),
                b"legacy bytes",
            )


if __name__ == "__main__":
    unittest.main()
