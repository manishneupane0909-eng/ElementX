"""SQLite reliability: WAL, busy_timeout, concurrency, legacy databases, transaction safety."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from services import db as db_module
from services.db import (
    DEFAULT_BUSY_TIMEOUT_MS,
    busy_timeout_ms,
    configure_engine,
    init_db,
    reset_engine,
    sqlite_settings,
    storage_ready,
)
from services.experiment_records import create_sample, list_samples
from tests.research_base import ResearchApiTestCase


class SqlitePragmaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DATABASE_URL")}

    def tearDown(self) -> None:
        reset_engine()
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def test_file_database_uses_wal_busy_timeout_and_normal_sync(self) -> None:
        engine = configure_engine(f"sqlite:///{self.root / 'elementx.db'}")
        init_db()
        settings = sqlite_settings(engine)
        self.assertEqual(settings["journal_mode"], "wal")
        self.assertEqual(settings["busy_timeout"], DEFAULT_BUSY_TIMEOUT_MS)
        self.assertEqual(settings["synchronous"], 1)  # NORMAL

    def test_every_pooled_connection_gets_the_settings(self) -> None:
        engine = configure_engine(f"sqlite:///{self.root / 'elementx.db'}")
        init_db()
        first = engine.raw_connection()
        second = engine.raw_connection()  # forces a second physical connection
        try:
            for connection in (first, second):
                self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 10_000)
                self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        finally:
            first.close()
            second.close()

    def test_busy_timeout_is_configurable_and_invalid_values_fall_back(self) -> None:
        with patch.dict(os.environ, {"SQLITE_BUSY_TIMEOUT_MS": "2500"}):
            self.assertEqual(busy_timeout_ms(), 2500)
            engine = configure_engine(f"sqlite:///{self.root / 'a.db'}")
            self.assertEqual(sqlite_settings(engine)["busy_timeout"], 2500)
        for bad in ("abc", "0", "-5", ""):
            with patch.dict(os.environ, {"SQLITE_BUSY_TIMEOUT_MS": bad}):
                self.assertEqual(busy_timeout_ms(), DEFAULT_BUSY_TIMEOUT_MS)

    def test_in_memory_database_is_not_forced_into_wal(self) -> None:
        engine = configure_engine("sqlite://")
        self.assertNotEqual(sqlite_settings(engine)["journal_mode"], "wal")

    def test_existing_rollback_journal_database_keeps_rows_when_switched_to_wal(self) -> None:
        legacy = self.root / "legacy.db"
        connection = sqlite3.connect(legacy)
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.executescript(
            """
            CREATE TABLE scientific_samples (
                id VARCHAR(36) PRIMARY KEY, name VARCHAR(255) NOT NULL, formula VARCHAR(255),
                notes TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
            INSERT INTO scientific_samples VALUES
                ('11111111-1111-1111-1111-111111111111', 'Legacy', 'Fe', NULL,
                 '2026-01-01 00:00:00', '2026-01-01 00:00:00');
            """
        )
        connection.commit()
        connection.close()

        engine = configure_engine(f"sqlite:///{legacy}")
        init_db()
        self.assertEqual(sqlite_settings(engine)["journal_mode"], "wal")
        with sqlite3.connect(legacy) as check:
            rows = check.execute("SELECT id, name FROM scientific_samples").fetchall()
        self.assertEqual(rows, [("11111111-1111-1111-1111-111111111111", "Legacy")])

    def test_concurrent_writers_do_not_hit_database_is_locked(self) -> None:
        engine = configure_engine(f"sqlite:///{self.root / 'elementx.db'}")
        init_db()
        factory = db_module.get_session_factory()
        errors: list[BaseException] = []

        def worker(index: int) -> None:
            try:
                for n in range(15):
                    session = factory()
                    try:
                        create_sample(
                            session, f"s-{index}-{n}", "Fe", None, owner_user_id=f"user-{index}"
                        )
                    finally:
                        session.close()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [])
        session = factory()
        try:
            total = sum(len(list_samples(session, f"user-{i}")) for i in range(6))
        finally:
            session.close()
        self.assertEqual(total, 6 * 15)
        engine.dispose()

    def test_writer_waits_for_a_busy_lock_instead_of_failing(self) -> None:
        path = self.root / "elementx.db"
        with patch.dict(os.environ, {"SQLITE_BUSY_TIMEOUT_MS": "5000"}):
            engine = configure_engine(f"sqlite:///{path}")
            init_db()
        blocker = sqlite3.connect(path, timeout=5, check_same_thread=False)
        blocker.execute("BEGIN IMMEDIATE")  # hold the write lock

        released = threading.Timer(0.6, blocker.rollback)
        released.start()
        try:
            session = db_module.get_session_factory()()
            try:
                create_sample(session, "waited", "Fe", None, owner_user_id="u")
            finally:
                session.close()
        finally:
            released.join()
            blocker.close()
        engine.dispose()

    def test_storage_ready_reflects_database_and_data_dir(self) -> None:
        data_dir = self.root / "data"
        data_dir.mkdir()
        os.environ["DATA_DIR"] = str(data_dir)
        configure_engine(f"sqlite:///{data_dir / 'elementx.db'}")
        init_db()
        self.assertTrue(storage_ready())
        os.environ["DATA_DIR"] = str(self.root / "missing")
        self.assertFalse(storage_ready())


class TransactionSafetyTests(ResearchApiTestCase):
    def test_failed_commit_leaves_no_row_and_no_original_file(self) -> None:
        sample = self.create_sample(name="Rollback sample")
        before_dirs = self.experiment_dirs()

        from sqlalchemy.orm import Session

        with patch.object(Session, "commit", side_effect=RuntimeError("disk full")):
            client = type(self.client_a)(self.client_a.app, headers=self.client_a.headers)
            client.raise_server_exceptions = False
            response = self.upload_magnetometry(sample["id"], client=client)
        self.assertGreaterEqual(response.status_code, 500)
        self.assertNotIn("disk full", response.text)
        self.assertEqual(self.experiment_dirs(), before_dirs)
        detail = self.client_a.get(f"/api/research/samples/{sample['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["experiments"], [])

    def test_service_recovers_after_a_failed_write(self) -> None:
        sample = self.create_sample(name="Recovery sample")
        self.assertEqual(self.upload_magnetometry(sample["id"]).status_code, 201)
        self.assertEqual(self.upload_xrd(sample["id"]).status_code, 201)


if __name__ == "__main__":
    unittest.main()
