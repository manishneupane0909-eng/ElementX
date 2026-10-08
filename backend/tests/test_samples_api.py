from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from tests.auth_helpers import USER_A_ID, auth_headers
from models.research import Experiment
from services.db import (
    configure_engine,
    get_db,
    get_session_factory,
    init_db,
    reset_engine,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

RESEARCH_SAMPLES = "/api/research/samples"
RESEARCH_EXPERIMENTS = "/api/research/experiments"


def _segment_300k(payload: dict) -> dict:
    for entry in payload["mh_analyses"]:
        temperature = entry["analysis"]["segment"].get("mean_temperature_K")
        if temperature is not None and abs(temperature - 300.0) < 5.0:
            return entry
    raise AssertionError("No ~300 K M-H segment found in analysis JSON.")


class SamplesPersistenceApiTests(unittest.TestCase):
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
        cls.client = TestClient(app, headers=auth_headers(USER_A_ID))
        cls.fixture_bytes = FIXTURE_PATH.read_bytes()

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

    def test_v2_samples_route_is_not_replaced(self) -> None:
        anonymous = TestClient(app)
        response = anonymous.get("/api/samples")
        self.assertEqual(response.status_code, 401)

    def test_create_sample_returns_uuid_and_fields(self) -> None:
        response = self._create_sample()

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        uuid.UUID(payload["id"])
        self.assertEqual(payload["name"], "Fe2CoGe annealed 48 h")
        self.assertEqual(payload["formula"], "Fe2CoGe")
        self.assertEqual(payload["notes"], "Annealed 900 C for 48 h")
        self.assertIn("created_at", payload)
        self.assertIn("updated_at", payload)
        self.assertEqual(payload["experiment_count"], 0)

    def test_list_samples_includes_created_sample(self) -> None:
        created = self._create_sample(name="List probe sample", formula=None, notes=None)
        sample_id = created.json()["id"]

        response = self.client.get(RESEARCH_SAMPLES)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIsInstance(payload, list)
        match = next(item for item in payload if item["id"] == sample_id)
        self.assertEqual(match["name"], "List probe sample")
        self.assertIsNone(match["formula"])
        self.assertNotIn("analysis_json", match)
        self.assertNotIn("experiments", match)

    def test_sample_detail_starts_with_zero_experiments(self) -> None:
        sample_id = self._create_sample(name="Empty sample").json()["id"]

        response = self.client.get(f"{RESEARCH_SAMPLES}/{sample_id}")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["id"], sample_id)
        self.assertEqual(payload["name"], "Empty sample")
        self.assertEqual(payload["experiments"], [])
        self.assertEqual(payload["experiment_count"], 0)
        self.assertNotIn("analysis_json", payload)

    def test_save_fe2coge_experiment_persists_analysis(self) -> None:
        sample_id = self._create_sample().json()["id"]

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/experiments",
            files={"file": (FIXTURE_PATH.name, self.fixture_bytes)},
        )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(payload["experiment_type"], "magnetometry")
        self.assertEqual(payload["original_filename"], FIXTURE_PATH.name)
        self.assertEqual(payload["analysis_version"], "1")
        self.assertNotIn("raw_file_path", payload)

        analysis = payload["analysis_json"]
        self.assertEqual(analysis["analysis_version"], "1")
        self.assertEqual(analysis["segmentation"]["segment_count"], 11)
        self.assertEqual(analysis["summary"]["mh_segment_count"], 10)
        self.assertEqual(analysis["summary"]["mt_segment_count"], 1)

        entry = _segment_300k(analysis)
        hysteresis = entry["analysis"]["hysteresis"]
        high_field = entry["analysis"]["high_field"]
        self.assertAlmostEqual(hysteresis["Hc_negative_Oe"], -107.452, places=3)
        self.assertAlmostEqual(hysteresis["Hc_positive_Oe"], 125.811, places=3)
        self.assertEqual(high_field["saturation_evidence_quality"], "high")

    def test_raw_file_is_preserved_on_generated_path(self) -> None:
        sample_id = self._create_sample(name="Raw file sample").json()["id"]
        malicious_name = f"..{os.sep}..{os.sep}evil.dat"

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/experiments",
            files={"file": (malicious_name, self.fixture_bytes)},
        )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        experiment_id = payload["id"]
        stored = self.data_dir / "experiments" / experiment_id / "original.dat"

        self.assertTrue(stored.exists())
        self.assertEqual(stored.read_bytes(), self.fixture_bytes)
        self.assertEqual(stored.name, "original.dat")
        self.assertEqual(payload["original_filename"], malicious_name)
        self.assertEqual(
            stored.resolve().parent,
            (self.data_dir / "experiments" / experiment_id).resolve(),
        )
        self.assertTrue(str(stored.resolve()).startswith(str(self.data_dir.resolve())))
        self.assertNotIn("evil.dat", str(stored))
        self.assertFalse((self.data_dir / "evil.dat").exists())
        self.assertFalse((self.data_dir.parent / "evil.dat").exists())

    def test_reopen_experiment_returns_full_analysis_json(self) -> None:
        sample_id = self._create_sample(name="Reopen sample").json()["id"]
        created = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/experiments",
            files={"file": (FIXTURE_PATH.name, self.fixture_bytes)},
        )
        experiment_id = created.json()["id"]

        response = self.client.get(f"{RESEARCH_EXPERIMENTS}/{experiment_id}")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertNotIn("raw_file_path", payload)
        analysis = payload["analysis_json"]
        self.assertIsInstance(analysis, dict)
        self.assertEqual(analysis["summary"]["mt_segment_count"], 1)
        self.assertEqual(analysis["summary"]["mh_segment_count"], 10)
        self.assertEqual(len(analysis["mh_analyses"]), 10)
        self.assertEqual(analysis["segmentation"]["segment_count"], 11)

        segments = analysis["segmentation"]["segments"]
        mt = [segment for segment in segments if segment["type"] == "M-T"]
        mh = [segment for segment in segments if segment["type"] == "M-H"]
        self.assertEqual(len(mt), 1)
        self.assertEqual(len(mh), 10)
        self.assertGreater(len(mt[0]["data"]["temperature_K"]), 0)
        self.assertGreater(len(mt[0]["data"]["moment_emu"]), 0)
        self.assertGreater(len(mh[0]["data"]["field_Oe"]), 0)
        self.assertGreater(len(mh[0]["data"]["moment_emu"]), 0)

        hysteresis = _segment_300k(analysis)["analysis"]["hysteresis"]
        self.assertAlmostEqual(hysteresis["Hc_negative_Oe"], -107.452, places=3)
        self.assertAlmostEqual(hysteresis["Hc_positive_Oe"], 125.811, places=3)

    def test_sample_detail_lists_experiment_summary_without_analysis_json(self) -> None:
        sample_id = self._create_sample(name="Summary sample").json()["id"]
        created = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/experiments",
            files={"file": (FIXTURE_PATH.name, self.fixture_bytes)},
        )
        experiment_id = created.json()["id"]

        response = self.client.get(f"{RESEARCH_SAMPLES}/{sample_id}")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertNotIn("analysis_json", payload)
        self.assertEqual(len(payload["experiments"]), 1)
        summary = payload["experiments"][0]
        self.assertEqual(summary["id"], experiment_id)
        self.assertEqual(summary["experiment_type"], "magnetometry")
        self.assertEqual(summary["original_filename"], FIXTURE_PATH.name)
        self.assertEqual(summary["analysis_version"], "1")
        self.assertIn("uploaded_at", summary)
        self.assertNotIn("analysis_json", summary)
        self.assertNotIn("raw_file_path", summary)
        self.assertLess(len(response.content), 20_000)

    def test_invalid_dat_does_not_leave_experiment_or_files(self) -> None:
        sample_id = self._create_sample(name="Failure cleanup").json()["id"]
        dirs_before = {path.name for path in self._experiment_dirs()}

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/experiments",
            files={"file": ("sample.dat", b"angle,intensity\n1,2\n3,4\n")},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn(
            "not a recognized Quantum Design .DAT file",
            response.json()["detail"],
        )

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

    def test_unknown_ids_return_404(self) -> None:
        missing_sample = str(uuid.uuid4())
        missing_experiment = str(uuid.uuid4())

        sample_response = self.client.get(f"{RESEARCH_SAMPLES}/{missing_sample}")
        self.assertEqual(sample_response.status_code, 404)
        self.assertEqual(sample_response.json()["detail"], "Sample not found.")
        self.assertNotIn("elementx.db", sample_response.text)
        self.assertNotIn(str(self.data_dir), sample_response.text)

        experiment_response = self.client.get(f"{RESEARCH_EXPERIMENTS}/{missing_experiment}")
        self.assertEqual(experiment_response.status_code, 404)
        self.assertEqual(experiment_response.json()["detail"], "Experiment not found.")

        upload_response = self.client.post(
            f"{RESEARCH_SAMPLES}/{missing_sample}/experiments",
            files={"file": (FIXTURE_PATH.name, self.fixture_bytes)},
        )
        self.assertEqual(upload_response.status_code, 404)
        self.assertEqual(upload_response.json()["detail"], "Sample not found.")

    def test_wrong_extension_is_rejected_without_persistence(self) -> None:
        sample_id = self._create_sample(name="Extension check").json()["id"]
        dirs_before = {path.name for path in self._experiment_dirs()}

        response = self.client.post(
            f"{RESEARCH_SAMPLES}/{sample_id}/experiments",
            files={"file": ("sample.csv", self.fixture_bytes)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only .dat files are supported", response.json()["detail"])
        detail = self.client.get(f"{RESEARCH_SAMPLES}/{sample_id}").json()
        self.assertEqual(detail["experiments"], [])
        self.assertEqual({path.name for path in self._experiment_dirs()}, dirs_before)


if __name__ == "__main__":
    unittest.main()
