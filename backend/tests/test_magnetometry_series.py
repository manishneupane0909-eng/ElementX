import math
import unittest
from pathlib import Path
from typing import Any

from services.magnetometry import segment_measurements
from services.magnetometry_analysis import analyze_quantum_design_magnetometry
from services.parsers.quantum_design import parse_quantum_design_dat

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

ORIGINAL_STYLE_FILENAME = "Fe2CoGe_annealed_5p4mg_48HRS_900C.dat"


def _assert_aligned_series(test: unittest.TestCase, data: dict[str, Any]) -> None:
    source_index = data["source_index"]
    length = len(source_index)
    test.assertEqual(len(data["temperature_K"]), length)
    test.assertEqual(len(data["field_Oe"]), length)
    test.assertEqual(len(data["moment_emu"]), length)
    test.assertGreater(length, 0)
    for index in range(1, length):
        test.assertGreater(source_index[index], source_index[index - 1])


class RealFe2CoGeSeriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = FIXTURE_PATH.read_text(encoding="utf-8", errors="ignore")
        cls.parsed = parse_quantum_design_dat(cls.text)
        cls.segmentation = segment_measurements(cls.parsed)
        cls.result = analyze_quantum_design_magnetometry(
            cls.text, filename=FIXTURE_PATH.name
        )
        cls.conflict = analyze_quantum_design_magnetometry(
            cls.text, filename=ORIGINAL_STYLE_FILENAME
        )
        cls.temperature = cls.parsed["data"]["Temperature (K)"]
        cls.field = cls.parsed["data"]["Magnetic Field (Oe)"]
        cls.moment = cls.parsed["data"]["Moment (emu)"]

    def _segment_300k(self, result: dict[str, Any]) -> dict[str, Any]:
        for entry in result["mh_analyses"]:
            temperature = entry["analysis"]["segment"].get("mean_temperature_K")
            if temperature is not None and abs(temperature - 300.0) < 5.0:
                return entry
        raise AssertionError("No ~300 K M-H segment found.")

    def test_segment_counts_unchanged(self) -> None:
        summary = self.result["summary"]
        self.assertEqual(self.result["segmentation"]["segment_count"], 11)
        self.assertEqual(summary["mt_segment_count"], 1)
        self.assertEqual(summary["mh_segment_count"], 10)
        self.assertEqual(summary["unknown_segment_count"], 0)

    def test_every_segment_has_aligned_series(self) -> None:
        for segment in self.result["segmentation"]["segments"]:
            _assert_aligned_series(self, segment["data"])

    def test_mh_series_preserve_acquisition_order_and_parsed_rows(self) -> None:
        for segment in self.segmentation["segments"]:
            if segment["type"] != "M-H":
                continue
            data = segment["data"]
            _assert_aligned_series(self, data)

            first = data["source_index"][0]
            last = data["source_index"][-1]
            self.assertGreaterEqual(first, segment["start_index"])
            self.assertLessEqual(last, segment["end_index"])
            self.assertEqual(data["temperature_K"][0], self.temperature[first])
            self.assertEqual(data["field_Oe"][0], self.field[first])
            self.assertEqual(data["moment_emu"][0], self.moment[first])
            self.assertEqual(data["temperature_K"][-1], self.temperature[last])
            self.assertEqual(data["field_Oe"][-1], self.field[last])
            self.assertEqual(data["moment_emu"][-1], self.moment[last])

            for offset, row in enumerate(data["source_index"]):
                self.assertEqual(data["temperature_K"][offset], self.temperature[row])
                self.assertEqual(data["field_Oe"][offset], self.field[row])
                self.assertEqual(data["moment_emu"][offset], self.moment[row])

            self.assertNotEqual(data["field_Oe"], sorted(data["field_Oe"]))

    def test_mt_series_preserve_alignment_and_parsed_rows(self) -> None:
        mt_segments = [
            segment
            for segment in self.segmentation["segments"]
            if segment["type"] == "M-T"
        ]
        self.assertEqual(len(mt_segments), 1)
        data = mt_segments[0]["data"]
        _assert_aligned_series(self, data)

        first = data["source_index"][0]
        last = data["source_index"][-1]
        self.assertEqual(data["temperature_K"][0], self.temperature[first])
        self.assertEqual(data["moment_emu"][0], self.moment[first])
        self.assertEqual(data["field_Oe"][0], self.field[first])
        self.assertEqual(data["temperature_K"][-1], self.temperature[last])
        self.assertEqual(data["moment_emu"][-1], self.moment[last])
        self.assertEqual(data["field_Oe"][-1], self.field[last])

        for offset, row in enumerate(data["source_index"]):
            self.assertTrue(math.isfinite(data["temperature_K"][offset]))
            self.assertTrue(math.isfinite(data["moment_emu"][offset]))
            self.assertTrue(math.isfinite(data["field_Oe"][offset]))
            self.assertEqual(data["field_Oe"][offset], self.field[row])

    def test_series_live_only_on_segmentation_not_mh_analyses(self) -> None:
        for entry in self.result["mh_analyses"]:
            self.assertNotIn("data", entry)
            self.assertNotIn("data", entry["analysis"])

    def test_hysteresis_at_300k_unchanged(self) -> None:
        entry = self._segment_300k(self.result)
        hysteresis = entry["analysis"]["hysteresis"]
        high_field = entry["analysis"]["high_field"]
        self.assertAlmostEqual(hysteresis["Hc_negative_Oe"], -107.452, places=3)
        self.assertAlmostEqual(hysteresis["Hc_positive_Oe"], 125.811, places=3)
        self.assertEqual(high_field["saturation_evidence_quality"], "high")

    def test_mass_provenance_unchanged(self) -> None:
        self.assertTrue(self.result["summary"]["normalization_available"])
        self.assertFalse(self.conflict["summary"]["normalization_available"])
        conflict_entry = self._segment_300k(self.conflict)
        self.assertEqual(
            conflict_entry["analysis"]["mass_provenance"]["resolution_status"],
            "conflict",
        )
        self.assertFalse(conflict_entry["analysis"]["normalized"]["available"])


class SyntheticSeriesOrderTests(unittest.TestCase):
    def test_mh_series_is_not_sorted_by_field(self) -> None:
        field = [-1000.0, 0.0, 1000.0, 500.0, -500.0, -1000.0]
        parsed = {
            "data": {
                "Temperature (K)": [300.0] * len(field),
                "Magnetic Field (Oe)": field,
                "Moment (emu)": [0.1, 0.2, 0.3, 0.25, 0.05, -0.1],
            }
        }
        result = segment_measurements(parsed)
        self.assertEqual(len(result["segments"]), 1)
        data = result["segments"][0]["data"]
        self.assertEqual(data["field_Oe"], field)
        self.assertEqual(data["source_index"], list(range(len(field))))
        self.assertNotEqual(data["field_Oe"], sorted(data["field_Oe"]))
