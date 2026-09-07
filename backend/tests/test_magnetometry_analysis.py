import unittest
from pathlib import Path
from typing import Any, Optional

from services.magnetometry_analysis import analyze_quantum_design_magnetometry

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

ORIGINAL_STYLE_FILENAME = "Fe2CoGe_annealed_5p4mg_48HRS_900C.dat"

FORBIDDEN_KEYS = {
    "Ms",
    "Ms_emu",
    "saturation_magnetization",
    "BHmax",
    "Tc",
    "Tc_K",
    "mu_B_per_formula_unit",
    "anisotropy",
}


def _collect_forbidden_keys(value: Any, found: Optional[set[str]] = None) -> set[str]:
    found = set() if found is None else found
    if isinstance(value, dict):
        found.update(key for key in value if key in FORBIDDEN_KEYS)
        for nested in value.values():
            _collect_forbidden_keys(nested, found)
    elif isinstance(value, list):
        for item in value:
            _collect_forbidden_keys(item, found)
    return found


def _segment_300k(result: dict[str, Any]) -> dict[str, Any]:
    for entry in result["mh_analyses"]:
        analysis = entry["analysis"]
        temperature = analysis["segment"].get("mean_temperature_K")
        if temperature is not None and abs(temperature - 300.0) < 5.0:
            return entry
    raise AssertionError("No ~300 K M-H segment found in analysis results.")


class RealFe2CoGeWholeFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = FIXTURE_PATH.read_text(encoding="utf-8", errors="ignore")
        cls.conflict = analyze_quantum_design_magnetometry(
            cls.text, filename=ORIGINAL_STYLE_FILENAME
        )
        cls.confirmed = analyze_quantum_design_magnetometry(
            cls.text,
            filename=ORIGINAL_STYLE_FILENAME,
            user_confirmed_mass_mg=5.4,
        )

    def test_parser_and_segmentation_succeed(self) -> None:
        self.assertEqual(self.conflict["file"]["format"], "quantum_design_dat")
        self.assertEqual(
            self.conflict["file"]["filename"], ORIGINAL_STYLE_FILENAME
        )
        self.assertEqual(self.conflict["metadata"]["SAMPLE_MASS"], "3.5")
        self.assertGreater(self.conflict["segmentation"]["segment_count"], 1)

    def test_segment_counts_by_type(self) -> None:
        summary = self.conflict["summary"]
        self.assertEqual(summary["mt_segment_count"], 1)
        self.assertEqual(summary["mh_segment_count"], 10)
        self.assertEqual(summary["unknown_segment_count"], 0)
        self.assertEqual(
            len(self.conflict["segmentation"]["segments"]),
            self.conflict["segmentation"]["segment_count"],
        )

    def test_every_mh_segment_receives_one_analysis(self) -> None:
        self.assertEqual(len(self.conflict["mh_analyses"]), 10)

        mh_indices = [entry["segment_index"] for entry in self.conflict["mh_analyses"]]
        expected_indices = [
            index
            for index, segment in enumerate(self.conflict["segmentation"]["segments"])
            if segment["type"] == "M-H"
        ]
        self.assertEqual(mh_indices, expected_indices)

        for entry in self.conflict["mh_analyses"]:
            analysis = entry["analysis"]
            self.assertEqual(analysis["segment_type"], "M-H")
            self.assertIn("hysteresis", analysis)
            self.assertIn("high_field", analysis)
            self.assertIn("mass_provenance", analysis)

    def test_mt_segments_are_not_analyzed_as_mh(self) -> None:
        mt_indices = {
            index
            for index, segment in enumerate(self.conflict["segmentation"]["segments"])
            if segment["type"] == "M-T"
        }
        analyzed_indices = {
            entry["segment_index"] for entry in self.conflict["mh_analyses"]
        }
        self.assertEqual(mt_indices & analyzed_indices, set())

        mt_segment = self.conflict["segmentation"]["segments"][0]
        self.assertEqual(mt_segment["type"], "M-T")

    def test_segment_ordering_is_preserved(self) -> None:
        segments = self.conflict["segmentation"]["segments"]
        self.assertEqual(segments[0]["type"], "M-T")
        self.assertTrue(all(segment["type"] == "M-H" for segment in segments[1:]))

    def test_300k_segment_matches_regression_values(self) -> None:
        entry = _segment_300k(self.conflict)
        hysteresis = entry["analysis"]["hysteresis"]
        high_field = entry["analysis"]["high_field"]

        self.assertEqual(entry["segment_index"], 8)
        self.assertAlmostEqual(hysteresis["Hc_negative_Oe"], -107.452, places=3)
        self.assertAlmostEqual(hysteresis["Hc_positive_Oe"], 125.811, places=3)
        self.assertAlmostEqual(
            high_field["maximum_absolute_measured_moment_emu"],
            0.449183614087668,
            places=9,
        )
        self.assertEqual(high_field["saturation_evidence_quality"], "high")

    def test_case_a_conflict_propagates_to_all_mh_analyses(self) -> None:
        self.assertFalse(self.conflict["summary"]["normalization_available"])

        for entry in self.conflict["mh_analyses"]:
            analysis = entry["analysis"]
            self.assertEqual(
                analysis["mass_provenance"]["resolution_status"], "conflict"
            )
            self.assertFalse(analysis["normalized"]["available"])
            self.assertIsNone(analysis["normalized"]["maximum_measured_moment"])
            self.assertIn("Hc_negative_Oe", analysis["hysteresis"])

    def test_case_b_hypothetical_confirmation_enables_normalization(self) -> None:
        """
        USER-CONFIRMED / HYPOTHETICAL.

        5.4 mg is supplied only to exercise normalization. It is not established
        as the experimentally correct sample mass for this file.
        """
        self.assertTrue(self.confirmed["summary"]["normalization_available"])

        for entry in self.confirmed["mh_analyses"]:
            analysis = entry["analysis"]
            self.assertEqual(
                analysis["mass_provenance"]["resolution_status"], "user_confirmed"
            )
            self.assertTrue(analysis["normalized"]["available"])
            self.assertIsNotNone(analysis["normalized"]["maximum_measured_moment"])

    def test_hypothetical_confirmation_does_not_change_raw_mh_values(self) -> None:
        for conflict_entry, confirmed_entry in zip(
            self.conflict["mh_analyses"], self.confirmed["mh_analyses"]
        ):
            self.assertEqual(
                conflict_entry["segment_index"], confirmed_entry["segment_index"]
            )
            for key in (
                "Hc_negative_Oe",
                "Hc_positive_Oe",
                "Mr_negative_emu",
                "Mr_positive_emu",
            ):
                self.assertEqual(
                    conflict_entry["analysis"]["hysteresis"][key],
                    confirmed_entry["analysis"]["hysteresis"][key],
                )
            for key in (
                "maximum_absolute_measured_moment_emu",
                "saturation_evidence_quality",
                "positive_relative_high_field_slope",
            ):
                self.assertEqual(
                    conflict_entry["analysis"]["high_field"][key],
                    confirmed_entry["analysis"]["high_field"][key],
                )

    def test_top_level_warnings_are_prefixed(self) -> None:
        warnings = self.conflict["warnings"]
        self.assertGreater(len(warnings), 0)
        allowed_prefixes = ("parser:", "segmentation:", "M-H segment ")
        for warning in warnings:
            self.assertTrue(
                warning.startswith(allowed_prefixes),
                f"Unexpected warning prefix: {warning!r}",
            )
        self.assertTrue(
            any(w.startswith("M-H segment 8:") for w in warnings),
            "Expected prefixed warnings from the ~300 K M-H segment.",
        )

    def test_underlying_warnings_are_preserved(self) -> None:
        entry = _segment_300k(self.conflict)
        self.assertIn("warnings", entry["analysis"])
        self.assertIn("warnings", self.conflict["segmentation"])

    def test_no_forbidden_quantities_are_returned(self) -> None:
        self.assertEqual(_collect_forbidden_keys(self.conflict), set())
        self.assertEqual(_collect_forbidden_keys(self.confirmed), set())

    def test_report_whole_file_summary(self) -> None:
        entry = _segment_300k(self.conflict)
        hysteresis = entry["analysis"]["hysteresis"]
        high_field = entry["analysis"]["high_field"]
        print(
            "\n".join(
                [
                    "",
                    "=== Fe2CoGe whole-file magnetometry analysis ===",
                    f"segment_count = {self.conflict['segmentation']['segment_count']}",
                    f"M-T segments  = {self.conflict['summary']['mt_segment_count']}",
                    f"M-H segments  = {self.conflict['summary']['mh_segment_count']}",
                    f"M-H analyses  = {len(self.conflict['mh_analyses'])}",
                    "",
                    "~300 K M-H segment (index 8):",
                    f"  Hc_negative_Oe = {hysteresis['Hc_negative_Oe']:.3f}",
                    f"  Hc_positive_Oe = {hysteresis['Hc_positive_Oe']:.3f}",
                    f"  maximum_absolute_measured_moment_emu = "
                    f"{high_field['maximum_absolute_measured_moment_emu']:.7f}",
                    f"  saturation_evidence_quality = "
                    f"{high_field['saturation_evidence_quality']}",
                    "",
                    "Conflict path:",
                    f"  normalization_available = "
                    f"{self.conflict['summary']['normalization_available']}",
                    "",
                    "USER-CONFIRMED / HYPOTHETICAL path (5.4 mg):",
                    f"  normalization_available = "
                    f"{self.confirmed['summary']['normalization_available']}",
                    "",
                ]
            )
        )
        self.assertEqual(len(self.conflict["mh_analyses"]), 10)


if __name__ == "__main__":
    unittest.main()
