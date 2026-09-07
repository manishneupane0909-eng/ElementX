import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import analyze_magnetometry_dat, app

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

ORIGINAL_STYLE_FILENAME = "Fe2CoGe_annealed_5p4mg_48HRS_900C.dat"


def _segment_300k(payload: dict) -> dict:
    for entry in payload["mh_analyses"]:
        temperature = entry["analysis"]["segment"].get("mean_temperature_K")
        if temperature is not None and abs(temperature - 300.0) < 5.0:
            return entry
    raise AssertionError("No ~300 K M-H segment found in HTTP response.")


class MagnetometryAnalyzeEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.fixture_bytes = FIXTURE_PATH.read_bytes()

    def _post_dat(
        self,
        filename: str,
        content: bytes | None = None,
        user_confirmed_mass_mg: float | None = None,
    ):
        data = {}
        if user_confirmed_mass_mg is not None:
            data["user_confirmed_mass_mg"] = str(user_confirmed_mass_mg)
        return self.client.post(
            "/api/magnetometry/analyze",
            files={"file": (filename, content if content is not None else self.fixture_bytes)},
            data=data,
        )

    def test_valid_real_dat_returns_full_analysis(self) -> None:
        response = self._post_dat(FIXTURE_PATH.name)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["file"]["format"], "quantum_design_dat")
        self.assertEqual(payload["file"]["filename"], FIXTURE_PATH.name)
        self.assertEqual(payload["summary"]["mt_segment_count"], 1)
        self.assertEqual(payload["summary"]["mh_segment_count"], 10)
        self.assertEqual(len(payload["mh_analyses"]), 10)

    def test_conflict_filename_blocks_normalization_but_succeeds(self) -> None:
        response = self._post_dat(ORIGINAL_STYLE_FILENAME)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertFalse(payload["summary"]["normalization_available"])

        entry = _segment_300k(payload)
        hysteresis = entry["analysis"]["hysteresis"]
        high_field = entry["analysis"]["high_field"]

        self.assertAlmostEqual(hysteresis["Hc_negative_Oe"], -107.452, places=3)
        self.assertAlmostEqual(hysteresis["Hc_positive_Oe"], 125.811, places=3)
        self.assertAlmostEqual(
            high_field["maximum_absolute_measured_moment_emu"],
            0.449183614087668,
            places=9,
        )
        self.assertEqual(high_field["saturation_evidence_quality"], "high")
        self.assertFalse(entry["analysis"]["normalized"]["available"])

    def test_user_confirmed_hypothetical_mass_enables_normalization(self) -> None:
        """
        USER-CONFIRMED / HYPOTHETICAL.

        5.4 mg is supplied only to exercise the HTTP normalization path. It is
        not established as the experimentally correct sample mass for this file.
        """
        response = self._post_dat(
            ORIGINAL_STYLE_FILENAME,
            user_confirmed_mass_mg=5.4,
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["summary"]["normalization_available"])

        entry = _segment_300k(payload)
        self.assertTrue(entry["analysis"]["normalized"]["available"])
        self.assertIsNotNone(
            entry["analysis"]["normalized"]["maximum_measured_moment"]
        )

    def test_wrong_extension_is_rejected(self) -> None:
        response = self._post_dat("sample.csv")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only .dat files are supported", response.json()["detail"])

    def test_non_quantum_design_dat_content_is_rejected(self) -> None:
        response = self._post_dat(
            "sample.dat",
            content=b"angle,intensity\n1,2\n3,4\n",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "not a recognized Quantum Design .DAT file",
            response.json()["detail"],
        )

    def test_missing_filename_is_rejected(self) -> None:
        # TestClient multipart uploads cannot deliver an empty filename to the
        # handler; exercise the route validation directly instead.
        file = MagicMock()
        file.filename = ""

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(analyze_magnetometry_dat(file, None))

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("filename is required", ctx.exception.detail)

    def test_invalid_confirmed_mass_is_rejected(self) -> None:
        response = self._post_dat(
            FIXTURE_PATH.name,
            user_confirmed_mass_mg=-5.4,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("negative", response.json()["detail"].lower())

    def test_config_objects_are_json_serializable(self) -> None:
        response = self._post_dat(FIXTURE_PATH.name)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        segmentation_config = payload["segmentation"]["config"]
        self.assertIsInstance(segmentation_config, dict)
        self.assertIn("temperature_noise_tolerance_K", segmentation_config)

        mh_config = payload["mh_analyses"][0]["analysis"]["high_field"]["config"]
        self.assertIsInstance(mh_config, dict)
        self.assertIn("high_field_fraction", mh_config)

    def test_report_http_summary(self) -> None:
        conflict = self._post_dat(ORIGINAL_STYLE_FILENAME).json()
        confirmed = self._post_dat(
            ORIGINAL_STYLE_FILENAME,
            user_confirmed_mass_mg=5.4,
        ).json()
        entry = _segment_300k(conflict)

        print(
            "\n".join(
                [
                    "",
                    "=== HTTP POST /api/magnetometry/analyze ===",
                    f"Conflict path: status=200 normalization_available="
                    f"{conflict['summary']['normalization_available']}",
                    f"Hypothetical confirmed: status=200 normalization_available="
                    f"{confirmed['summary']['normalization_available']}",
                    f"~300 K Hc_negative_Oe = {entry['analysis']['hysteresis']['Hc_negative_Oe']:.3f}",
                    f"~300 K Hc_positive_Oe = {entry['analysis']['hysteresis']['Hc_positive_Oe']:.3f}",
                    f"~300 K maximum_absolute_measured_moment_emu = "
                    f"{entry['analysis']['high_field']['maximum_absolute_measured_moment_emu']:.7f}",
                    "",
                ]
            )
        )
        self.assertEqual(conflict["summary"]["normalization_available"], False)
        self.assertEqual(confirmed["summary"]["normalization_available"], True)


class LegacyEndpointImportTests(unittest.TestCase):
    def test_legacy_magnetic_upload_route_still_exists(self) -> None:
        routes = {route.path for route in app.routes if hasattr(route, "path")}
        self.assertIn("/api/magnetic/upload", routes)
        self.assertIn("/api/magnetometry/analyze", routes)


if __name__ == "__main__":
    unittest.main()
