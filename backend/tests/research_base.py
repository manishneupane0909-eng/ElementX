"""Shared fixtures for authenticated research-API tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from services.db import (
    configure_engine,
    get_db,
    get_session_factory,
    init_db,
    reset_engine,
)
from tests.auth_helpers import USER_A_ID, USER_B_ID, auth_headers

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MAGNETOMETRY_FIXTURE = FIXTURES / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
XRD_FIXTURE = FIXTURES / "two_column_xrd_test.xy"

RESEARCH_SAMPLES = "/api/research/samples"
RESEARCH_EXPERIMENTS = "/api/research/experiments"


class ResearchApiTestCase(unittest.TestCase):
    """Fresh SQLite DB + data dir per test class, with clients for users A and B."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls._tmpdir.name)
        cls.db_path = root / "elementx.db"
        cls.data_dir = root / "data"
        cls._prev_env = {k: os.environ.get(k) for k in ("DATABASE_URL", "DATA_DIR")}
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.db_path}"
        os.environ["DATA_DIR"] = str(cls.data_dir)
        cls.restart_engine()

        def override_get_db():
            db = get_session_factory()()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.anonymous = TestClient(app)
        cls.client_a = TestClient(app, headers=auth_headers(USER_A_ID))
        cls.client_b = TestClient(app, headers=auth_headers(USER_B_ID))
        cls.magnetometry_bytes = MAGNETOMETRY_FIXTURE.read_bytes()
        cls.xrd_bytes = XRD_FIXTURE.read_bytes()

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_db, None)
        reset_engine()
        for key, value in cls._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls._tmpdir.cleanup()

    @classmethod
    def restart_engine(cls) -> None:
        """Simulate a backend restart: drop engine state and reopen the same files."""
        reset_engine()
        configure_engine(os.environ["DATABASE_URL"])
        init_db()

    def experiment_dirs(self) -> set[str]:
        experiments = self.data_dir / "experiments"
        if not experiments.exists():
            return set()
        return {path.name for path in experiments.iterdir() if path.is_dir()}

    def create_sample(self, client: TestClient | None = None, **overrides) -> dict:
        body = {"name": "Ownership sample", "formula": "Fe2CoGe", "notes": None}
        body.update(overrides)
        response = (client or self.client_a).post(RESEARCH_SAMPLES, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def upload_magnetometry(self, sample_id: str, client: TestClient | None = None):
        return (client or self.client_a).post(
            f"{RESEARCH_SAMPLES}/{sample_id}/experiments",
            files={"file": (MAGNETOMETRY_FIXTURE.name, self.magnetometry_bytes)},
        )

    def upload_xrd(self, sample_id: str, client: TestClient | None = None):
        return (client or self.client_a).post(
            f"{RESEARCH_SAMPLES}/{sample_id}/xrd-experiments",
            files={"file": (XRD_FIXTURE.name, self.xrd_bytes)},
        )
