from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from models.research import Experiment
from services.db import (
    configure_engine,
    get_db,
    get_session_factory,
    init_db,
    reset_engine,
)

XRD_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "two_column_xrd_test.xy"
)
MAGNETOMETRY_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

RESEARCH_SAMPLES = "/api/research/samples"
RESEARCH_EXPERIMENTS = "/api/research/experiments"


class XrdPersistenceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls._tmpdir.name)
        cls.db_path = root / "elementx.db"
        cls.data_dir = root / "data"
        cls._prev_database_url = os.environ.get("DATABASE_URL")
        cls._prev_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.db_path}"
        os.environ["DATA_DIR"] = str(cls.data_dir)

        reset_engine()
        configure_engine(os.environ["DATABASE_URL"])
        init_db()

        def override_get_db():
            db = get_session_factory()()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.xrd_bytes = XRD_FIXTURE_PATH.read_bytes()
        cls.magnetometry_bytes = MAGNETOMETRY_FIXTURE_PATH.read_bytes()

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_db, None)
        reset_engine()
        if cls._prev_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls._prev_database_url
        if cls._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = cls._prev_data_dir
        cls._tmpdir.cleanup()

    def _experiment_dirs(self) -> list[Path]:
        experiments = self.data_dir / "experiments"
        if not experiments.exists():
            return []
        return [path for path in experiments.iterdir() if path.is_dir()]

    def _create_sample(self, **overrides):
        body = {
            "name": "Fe2CoGe annealed 48 h",
            "formula": "Fe2CoGe",
            "notes": "Annealed 900 C for 48 h",
        }
        body.update(overrides)
        return self.client.post(RESEARCH_SAMPLES, json=body)

    def test_save_xrd_experiment_persists_analysis(self) -> None:
        sample_id = self._create_sample(name="XRD save sample").json()["id"]

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/xrd-experiments",
            files={"file": (XRD_FIXTURE_PATH.name, self.xrd_bytes)},
        )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(payload["experiment_type"], "xrd")
        self.assertEqual(payload["analysis_version"], "1")
        self.assertEqual(payload["original_filename"], XRD_FIXTURE_PATH.name)
        self.assertIsNone(payload["user_confirmed_mass_mg"])
        self.assertNotIn("raw_file_path", payload)

        analysis = payload["analysis_json"]
        self.assertEqual(analysis["analysis_version"], "1")
        self.assertEqual(analysis["file"]["format"], "two_column_xrd_text")
        self.assertEqual(analysis["summary"]["point_count"], 40)
        self.assertEqual(analysis["peak_detection"]["label"], "candidate_intensity_maxima")
        self.assertNotIn("phaseAnalysis", analysis)
        self.assertNotIn("hkl", analysis)

    def test_raw_xrd_file_is_preserved_on_generated_path(self) -> None:
        sample_id = self._create_sample(name="XRD raw sample").json()["id"]
        malicious_name = f"..{os.sep}..{os.sep}evil.xy"

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/xrd-experiments",
            files={"file": (malicious_name, self.xrd_bytes)},
        )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        experiment_id = payload["id"]
        stored = self.data_dir / "experiments" / experiment_id / "original.xy"

        self.assertTrue(stored.exists())
        self.assertEqual(stored.read_bytes(), self.xrd_bytes)
        self.assertEqual(stored.name, "original.xy")
        self.assertEqual(payload["original_filename"], malicious_name)
        self.assertEqual(
            stored.resolve().parent,
            (self.data_dir / "experiments" / experiment_id).resolve(),
        )
        self.assertTrue(str(stored.resolve()).startswith(str(self.data_dir.resolve())))
        self.assertNotIn("evil.xy", str(stored))
        self.assertFalse((self.data_dir / "evil.xy").exists())
        self.assertFalse((self.data_dir.parent / "evil.xy").exists())

    def test_reopen_xrd_experiment_returns_stored_series(self) -> None:
        sample_id = self._create_sample(name="XRD reopen sample").json()["id"]
        created = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/xrd-experiments",
            files={"file": (XRD_FIXTURE_PATH.name, self.xrd_bytes)},
        )
        experiment_id = created.json()["id"]
        created_series = created.json()["analysis_json"]["series"]

        response = self.client.get(f"{RESEARCH_EXPERIMENTS}/{experiment_id}")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["experiment_type"], "xrd")
        analysis = payload["analysis_json"]
        self.assertEqual(analysis["series"]["two_theta_deg"], created_series["two_theta_deg"])
        self.assertEqual(analysis["series"]["intensity"], created_series["intensity"])
        self.assertEqual(analysis["summary"]["point_count"], 40)

    def test_mixed_sample_lists_magnetometry_and_xrd(self) -> None:
        sample_id = self._create_sample(name="Mixed sample").json()["id"]

        magnetometry = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/experiments",
            files={"file": (MAGNETOMETRY_FIXTURE_PATH.name, self.magnetometry_bytes)},
        )
        xrd = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/xrd-experiments",
            files={"file": (XRD_FIXTURE_PATH.name, self.xrd_bytes)},
        )

        self.assertEqual(magnetometry.status_code, 201, magnetometry.text)
        self.assertEqual(xrd.status_code, 201, xrd.text)

        detail = self.client.get(f"{RESEARCH_SAMPLES}/{sample_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        payload = detail.json()
        types = {item["experiment_type"] for item in payload["experiments"]}
        self.assertEqual(types, {"magnetometry", "xrd"})
        self.assertEqual(payload["experiment_count"], 2)
        self.assertNotIn("analysis_json", payload)
        for summary in payload["experiments"]:
            self.assertNotIn("analysis_json", summary)
            self.assertNotIn("raw_file_path", summary)

    def test_invalid_xrd_does_not_leave_experiment_or_files(self) -> None:
        sample_id = self._create_sample(name="XRD failure cleanup").json()["id"]
        dirs_before = {path.name for path in self._experiment_dirs()}

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/xrd-experiments",
            files={"file": ("empty.xy", b"# no data\n")},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("too few", response.json()["detail"])

        detail = self.client.get(f"{RESEARCH_SAMPLES}/{sample_id}").json()
        self.assertEqual(detail["experiments"], [])

        db = get_session_factory()()
        try:
            rows = db.query(Experiment).filter(Experiment.sample_id == sample_id).all()
            self.assertEqual(rows, [])
        finally:
            db.close()

        dirs_after = {path.name for path in self._experiment_dirs()}
        self.assertEqual(dirs_after, dirs_before)

    def test_quantum_design_dat_is_rejected_as_xrd_upload(self) -> None:
        sample_id = self._create_sample(name="QD as XRD").json()["id"]
        dirs_before = {path.name for path in self._experiment_dirs()}

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/xrd-experiments",
            files={"file": (MAGNETOMETRY_FIXTURE_PATH.name, self.magnetometry_bytes)},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Quantum Design", response.json()["detail"])
        self.assertEqual(
            self.client.get(f"{RESEARCH_SAMPLES}/{sample_id}").json()["experiments"],
            [],
        )
        self.assertEqual({path.name for path in self._experiment_dirs()}, dirs_before)

    def test_unsupported_xrd_extension_is_rejected(self) -> None:
        sample_id = self._create_sample(name="XRD extension check").json()["id"]
        dirs_before = {path.name for path in self._experiment_dirs()}

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/xrd-experiments",
            files={"file": ("scan.ras", self.xrd_bytes)},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Only .txt, .csv, .xy", response.json()["detail"])
        self.assertEqual(
            self.client.get(f"{RESEARCH_SAMPLES}/{sample_id}").json()["experiments"],
            [],
        )
        self.assertEqual({path.name for path in self._experiment_dirs()}, dirs_before)

    def test_legacy_xrd_upload_route_still_requires_auth(self) -> None:
        response = self.client.post(
            "/api/xrd/upload",
            files={"file": (XRD_FIXTURE_PATH.name, self.xrd_bytes)},
        )
        self.assertEqual(response.status_code, 401)

    def test_unknown_sample_returns_404_for_xrd_upload(self) -> None:
        missing_sample = str(uuid.uuid4())
        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{missing_sample}/xrd-experiments",
            files={"file": (XRD_FIXTURE_PATH.name, self.xrd_bytes)},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Sample not found.")


if __name__ == "__main__":
    unittest.main()
