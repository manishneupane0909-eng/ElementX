from __future__ import annotations

import os
from unittest.mock import patch

from tests.research_base import RESEARCH_SAMPLES, ResearchApiTestCase

ONE_KB_LIMIT_MB = "0.001"  # ~1 KiB


class UploadLimitTests(ResearchApiTestCase):
    def test_oversized_magnetometry_upload_is_rejected_with_clear_error(self) -> None:
        sample = self.create_sample(name="Size limit magnetometry")
        dirs_before = self.experiment_dirs()
        with patch.dict(os.environ, {"MAX_UPLOAD_MB": ONE_KB_LIMIT_MB}):
            response = self.upload_magnetometry(sample["id"])

        self.assertEqual(response.status_code, 413, response.text)
        detail = response.json()["detail"]
        self.assertIn("too large", detail)
        self.assertIn("maximum upload size", detail)
        self.assertEqual(self.experiment_dirs(), dirs_before)
        reopened = self.client_a.get(f"{RESEARCH_SAMPLES}/{sample['id']}").json()
        self.assertEqual(reopened["experiments"], [])

    def test_oversized_xrd_upload_is_rejected_without_persistence(self) -> None:
        sample = self.create_sample(name="Size limit xrd")
        big = b"20.0 10\n" * 1000  # ~8 KB
        dirs_before = self.experiment_dirs()
        with patch.dict(os.environ, {"MAX_UPLOAD_MB": ONE_KB_LIMIT_MB}):
            response = self.client_a.post(
                f"{RESEARCH_SAMPLES}/{sample['id']}/xrd-experiments",
                files={"file": ("big.xy", big)},
            )
        self.assertEqual(response.status_code, 413, response.text)
        self.assertIn("too large", response.json()["detail"])
        self.assertEqual(self.experiment_dirs(), dirs_before)

    def test_error_does_not_leak_filename_or_paths(self) -> None:
        sample = self.create_sample(name="No leak")
        with patch.dict(os.environ, {"MAX_UPLOAD_MB": ONE_KB_LIMIT_MB}):
            response = self.client_a.post(
                f"{RESEARCH_SAMPLES}/{sample['id']}/xrd-experiments",
                files={"file": ("secret-project-name.xy", b"1 2\n" * 1000)},
            )
        self.assertNotIn("secret-project-name", response.text)
        self.assertNotIn(str(self.data_dir), response.text)

    def test_default_limit_accepts_real_files(self) -> None:
        sample = self.create_sample(name="Within limit")
        self.assertEqual(self.upload_magnetometry(sample["id"]).status_code, 201)
        self.assertEqual(self.upload_xrd(sample["id"]).status_code, 201)

    def test_stateless_magnetometry_analyze_honours_limit(self) -> None:
        with patch.dict(os.environ, {"MAX_UPLOAD_MB": ONE_KB_LIMIT_MB}):
            response = self.anonymous.post(
                "/api/magnetometry/analyze",
                files={"file": ("x.dat", self.magnetometry_bytes)},
            )
        self.assertEqual(response.status_code, 413, response.text)

    def test_cif_upload_honours_limit(self) -> None:
        with patch.dict(os.environ, {"MAX_CIF_UPLOAD_MB": ONE_KB_LIMIT_MB}):
            response = self.anonymous.post(
                "/api/parse-cif",
                files={"file": ("big.cif", b"data_x\n" + b"# padding\n" * 500)},
            )
        self.assertEqual(response.status_code, 413, response.text)
        self.assertIn("too large", response.json()["detail"])

    def test_invalid_limit_env_falls_back_to_default(self) -> None:
        sample = self.create_sample(name="Bad env")
        with patch.dict(os.environ, {"MAX_UPLOAD_MB": "not-a-number"}):
            response = self.upload_xrd(sample["id"])
        self.assertEqual(response.status_code, 201, response.text)
