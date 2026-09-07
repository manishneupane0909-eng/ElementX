import unittest
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

from services.magnetometry import segment_measurements
from services.mass_normalization import MassNormalizationError
from services.mh_analysis import (
    MHAnalysisError,
    _build_normalized_results,
    analyze_mh_segment,
)
from services.parsers.quantum_design import parse_quantum_design_dat

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
    "mu_B_per_formula_unit",
    "bohr_magnetons_per_formula_unit",
}


def _loop_fields(step: float = 1500.0) -> list[float]:
    maximum = 30_000.0
    count = int(2 * maximum / step)
    descending = [maximum - step * index for index in range(count + 1)]
    ascending = [-maximum + step * index for index in range(1, count + 1)]
    return descending + ascending


def _loop_moments(fields: list[float], susceptibility: float = 1e-7) -> list[float]:
    import math

    return [
        0.45 * math.tanh(value / 2_000.0) + susceptibility * value
        for value in fields
    ]


def _parsed(fields: list[float], moments: list[float]) -> dict[str, Any]:
    return {
        "data": {
            "Temperature (K)": [300.0] * len(fields),
            "Magnetic Field (Oe)": fields,
            "Moment (emu)": moments,
        },
        "metadata": {"SAMPLE_MASS": "3.5"},
    }


def _segment(fields: list[float], segment_type: str = "M-H") -> dict[str, Any]:
    return {
        "type": segment_type,
        "start_index": 0,
        "end_index": len(fields) - 1,
        "mean_temperature_K": 300.0,
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


class ValidationTests(unittest.TestCase):
    def test_rejects_non_mh_segment(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields)
        with self.assertRaises(MHAnalysisError) as ctx:
            analyze_mh_segment(
                _parsed(fields, moments), _segment(fields, segment_type="M-T")
            )
        self.assertIn("M-H", str(ctx.exception))
        self.assertIn("M-T", str(ctx.exception))

    def test_invalid_parsed_input_raises(self) -> None:
        fields = _loop_fields()
        with self.assertRaises(MHAnalysisError):
            analyze_mh_segment(["not", "a", "dict"], _segment(fields))

    def test_invalid_segment_input_raises(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields)
        with self.assertRaises(MHAnalysisError):
            analyze_mh_segment(_parsed(fields, moments), ["not", "a", "dict"])


class SyntheticPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fields = _loop_fields()
        self.moments = _loop_moments(self.fields)
        self.parsed = _parsed(self.fields, self.moments)
        self.segment = _segment(self.fields)
        self.result = analyze_mh_segment(self.parsed, self.segment)

    def test_pipeline_nests_complete_module_outputs(self) -> None:
        self.assertEqual(self.result["segment_type"], "M-H")
        self.assertIn("Hc_negative_Oe", self.result["hysteresis"])
        self.assertIn("Mr_positive_emu", self.result["hysteresis"])
        self.assertIn("maximum_absolute_measured_moment_emu", self.result["high_field"])
        self.assertIn("saturation_evidence_quality", self.result["high_field"])
        self.assertIn("mass_candidates", self.result["mass_provenance"])
        self.assertIn("resolution_status", self.result["mass_provenance"])

    def test_segment_summary_is_reported(self) -> None:
        self.assertEqual(self.result["segment"]["start_index"], 0)
        self.assertEqual(self.result["segment"]["end_index"], len(self.fields) - 1)
        self.assertAlmostEqual(self.result["segment"]["mean_temperature_K"], 300.0)

    def test_authorized_mass_enables_normalization(self) -> None:
        self.assertTrue(self.result["mass_provenance"]["normalization_allowed"])
        self.assertTrue(self.result["normalized"]["available"])

        normalized = self.result["normalized"]
        self.assertIsNotNone(normalized["maximum_measured_moment"])
        self.assertIn(
            "specific_magnetization_emu_per_g",
            normalized["maximum_measured_moment"],
        )
        if self.result["hysteresis"]["Mr_positive_emu"] is not None:
            self.assertIsNotNone(normalized["Mr_positive"])

    def test_warnings_are_aggregated_with_source_prefixes(self) -> None:
        for warning in self.result["warnings"]:
            self.assertTrue(
                warning.startswith(
                    ("hysteresis: ", "high_field: ", "mass_provenance: ")
                ),
                f"Unexpected warning prefix: {warning!r}",
            )

    def test_no_forbidden_quantities_are_returned(self) -> None:
        self.assertEqual(_collect_forbidden_keys(self.result), set())


class NormalizationIntegrityTests(unittest.TestCase):
    def _sample_modules(self) -> tuple[dict[str, Any], dict[str, Any]]:
        hysteresis = {
            "Mr_negative_emu": -0.01,
            "Mr_positive_emu": 0.02,
        }
        high_field = {
            "maximum_absolute_measured_moment_emu": 0.45,
            "moment_at_max_positive_field_emu": 0.45,
            "moment_at_max_negative_field_emu": -0.45,
        }
        return hysteresis, high_field

    def test_conflict_provenance_leaves_normalization_unavailable(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields)
        result = analyze_mh_segment(
            _parsed(fields, moments),
            _segment(fields),
            filename=ORIGINAL_STYLE_FILENAME,
        )

        self.assertIn("Hc_negative_Oe", result["hysteresis"])
        self.assertIn("maximum_absolute_measured_moment_emu", result["high_field"])
        self.assertEqual(result["mass_provenance"]["resolution_status"], "conflict")
        self.assertFalse(result["normalized"]["available"])
        self.assertIsNone(result["normalized"]["maximum_measured_moment"])

    def test_authorized_provenance_enables_normalization(self) -> None:
        hysteresis, high_field = self._sample_modules()
        provenance = {
            "normalization_allowed": True,
            "resolution_status": "instrument_metadata",
            "resolved_mass_mg": 3.5,
            "resolved_source": "instrument_header",
        }

        normalized = _build_normalized_results(hysteresis, high_field, provenance)

        self.assertTrue(normalized["available"])
        self.assertIsNotNone(normalized["maximum_measured_moment"])
        self.assertAlmostEqual(
            normalized["maximum_measured_moment"]["specific_magnetization_emu_per_g"],
            0.45 / 0.0035,
            places=9,
        )

    def test_authorized_normalization_failure_raises_with_chained_error(self) -> None:
        hysteresis, high_field = self._sample_modules()
        provenance = {
            "normalization_allowed": True,
            "resolution_status": "instrument_metadata",
            "resolved_mass_mg": 3.5,
            "resolved_source": "instrument_header",
        }

        with patch(
            "services.mh_analysis.normalize_moment_by_mass",
            side_effect=MassNormalizationError("unexpected contract failure"),
        ):
            with self.assertRaises(MHAnalysisError) as ctx:
                _build_normalized_results(hysteresis, high_field, provenance)

        message = str(ctx.exception)
        self.assertIn("authorized normalization", message)
        self.assertIn("unexpected contract failure", message)
        self.assertIsInstance(ctx.exception.__cause__, MassNormalizationError)


class RealFe2CoGeMHAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parsed = parse_quantum_design_dat(
            FIXTURE_PATH.read_text(encoding="utf-8", errors="ignore")
        )
        segmented = segment_measurements(cls.parsed)
        cls.segment = min(
            (s for s in segmented["segments"] if s["type"] == "M-H"),
            key=lambda s: abs(s["mean_temperature_K"] - 300.0),
        )
        cls.conflict = analyze_mh_segment(
            cls.parsed, cls.segment, filename=ORIGINAL_STYLE_FILENAME
        )
        cls.confirmed = analyze_mh_segment(
            cls.parsed,
            cls.segment,
            filename=ORIGINAL_STYLE_FILENAME,
            user_confirmed_mass_mg=5.4,
        )

    def test_segment_is_the_300k_loop(self) -> None:
        self.assertAlmostEqual(self.segment["mean_temperature_K"], 300.0, delta=5.0)

    def test_case1_conflict_still_returns_full_raw_analysis(self) -> None:
        self.assertEqual(
            self.conflict["mass_provenance"]["resolution_status"], "conflict"
        )
        self.assertFalse(self.conflict["normalized"]["available"])
        self.assertEqual(self.conflict["normalized"]["reason"], "conflict")

        hysteresis = self.conflict["hysteresis"]
        high_field = self.conflict["high_field"]

        self.assertAlmostEqual(hysteresis["Hc_negative_Oe"], -107.452, places=3)
        self.assertAlmostEqual(hysteresis["Hc_positive_Oe"], 125.811, places=3)
        self.assertAlmostEqual(hysteresis["Mr_negative_emu"], -0.017291, places=6)
        self.assertAlmostEqual(hysteresis["Mr_positive_emu"], 0.015499, places=6)
        self.assertAlmostEqual(
            high_field["maximum_absolute_measured_moment_emu"],
            0.449183614087668,
            places=9,
        )
        self.assertEqual(high_field["saturation_evidence_quality"], "high")

        normalized = self.conflict["normalized"]
        self.assertIsNone(normalized["Mr_negative"])
        self.assertIsNone(normalized["Mr_positive"])
        self.assertIsNone(normalized["maximum_measured_moment"])
        self.assertIsNone(normalized["moment_at_max_positive_field"])
        self.assertIsNone(normalized["moment_at_max_negative_field"])

    def test_case2_user_confirmed_hypothetical_normalization(self) -> None:
        """
        USER-CONFIRMED / HYPOTHETICAL.

        5.4 mg is supplied only to exercise normalization. It is not established
        as the experimentally correct sample mass for this file.
        """
        self.assertTrue(self.confirmed["mass_provenance"]["normalization_allowed"])
        self.assertEqual(
            self.confirmed["mass_provenance"]["resolution_status"], "user_confirmed"
        )
        self.assertTrue(self.confirmed["normalized"]["available"])

        normalized = self.confirmed["normalized"]
        mr_positive = self.confirmed["hysteresis"]["Mr_positive_emu"]
        maximum_moment = self.confirmed["high_field"][
            "maximum_absolute_measured_moment_emu"
        ]
        self.assertAlmostEqual(
            normalized["Mr_positive"]["specific_magnetization_emu_per_g"],
            mr_positive / 0.0054,
            places=6,
        )
        self.assertAlmostEqual(
            normalized["maximum_measured_moment"]["specific_magnetization_emu_per_g"],
            maximum_moment / 0.0054,
            places=6,
        )
        self.assertEqual(_collect_forbidden_keys(self.confirmed), set())

    def test_changing_mass_does_not_change_raw_physics(self) -> None:
        for key in (
            "Hc_negative_Oe",
            "Hc_positive_Oe",
            "Mr_negative_emu",
            "Mr_positive_emu",
            "coercive_center_shift_Oe",
            "coercive_half_width_Oe",
        ):
            self.assertEqual(
                self.conflict["hysteresis"][key],
                self.confirmed["hysteresis"][key],
                f"Raw hysteresis field {key} changed with mass confirmation.",
            )

        for key in (
            "maximum_absolute_measured_moment_emu",
            "moment_at_max_positive_field_emu",
            "moment_at_max_negative_field_emu",
            "positive_high_field_slope_emu_per_Oe",
            "negative_high_field_slope_emu_per_Oe",
            "positive_high_field_extrapolated_intercept_emu",
            "negative_high_field_extrapolated_intercept_emu",
            "positive_high_field_r_squared",
            "negative_high_field_r_squared",
            "positive_relative_high_field_slope",
            "negative_relative_high_field_slope",
            "saturation_evidence_quality",
        ):
            self.assertEqual(
                self.conflict["high_field"][key],
                self.confirmed["high_field"][key],
                f"Raw high-field quantity {key} changed with mass confirmation.",
            )

    def test_mass_conflict_warning_survives_in_aggregated_warnings(self) -> None:
        self.assertTrue(
            any(
                w.startswith("mass_provenance:") and "disagree" in w
                for w in self.conflict["warnings"]
            )
        )

    def test_report_real_file_summary(self) -> None:
        hysteresis = self.conflict["hysteresis"]
        high_field = self.conflict["high_field"]
        print(
            "\n".join(
                [
                    "",
                    "=== Fe2CoGe ~300 K unified M-H analysis ===",
                    f"segment rows {self.segment['start_index']}-{self.segment['end_index']}, "
                    f"T = {self.segment['mean_temperature_K']:.2f} K",
                    "",
                    "Raw hysteresis:",
                    f"  Hc_negative_Oe = {hysteresis['Hc_negative_Oe']:.3f}",
                    f"  Hc_positive_Oe = {hysteresis['Hc_positive_Oe']:.3f}",
                    f"  Mr_negative_emu = {hysteresis['Mr_negative_emu']:.6f}",
                    f"  Mr_positive_emu = {hysteresis['Mr_positive_emu']:.6f}",
                    "",
                    "Raw high-field:",
                    f"  maximum_absolute_measured_moment_emu = "
                    f"{high_field['maximum_absolute_measured_moment_emu']:.7f}",
                    f"  saturation_evidence_quality = "
                    f"{high_field['saturation_evidence_quality']}",
                    "",
                    "Conflict path:",
                    f"  resolution_status = {self.conflict['mass_provenance']['resolution_status']}",
                    f"  normalized.available = {self.conflict['normalized']['available']}",
                    "",
                    "USER-CONFIRMED / HYPOTHETICAL path (5.4 mg):",
                    f"  normalized.available = {self.confirmed['normalized']['available']}",
                    f"  Mr_positive specific magnetization = "
                    f"{self.confirmed['normalized']['Mr_positive']['specific_magnetization_emu_per_g']:.6f} emu/g",
                    f"  maximum measured moment specific magnetization = "
                    f"{self.confirmed['normalized']['maximum_measured_moment']['specific_magnetization_emu_per_g']:.6f} emu/g",
                    "  (mass-normalized measured quantities, NOT Ms)",
                    "",
                ]
            )
        )
        self.assertFalse(self.conflict["normalized"]["available"])
        self.assertTrue(self.confirmed["normalized"]["available"])


if __name__ == "__main__":
    unittest.main()
