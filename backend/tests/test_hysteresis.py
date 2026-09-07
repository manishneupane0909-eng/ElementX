import math
import unittest
from pathlib import Path
from typing import Any, Optional

from services.hysteresis import (
    DEFAULT_CONFIG,
    HysteresisAnalysisError,
    HysteresisConfig,
    analyze_hysteresis,
)
from services.magnetometry import segment_measurements
from services.parsers.quantum_design import parse_quantum_design_dat

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

FORBIDDEN_KEYS = {
    "Ms",
    "Ms_emu",
    "BHmax",
    "Tc",
    "Tc_K",
    "saturation_magnetization",
    "moment_per_gram",
    "emu_per_gram",
    "anisotropy",
    "demagnetization_factor",
}


def _parsed(field: list[float], moment: list[float], temperature: float = 300.0) -> dict:
    return {
        "data": {
            "Temperature (K)": [temperature] * len(field),
            "Magnetic Field (Oe)": field,
            "Moment (emu)": moment,
        }
    }


def _segment(
    field: list[float],
    segment_type: str = "M-H",
    start: int = 0,
    end: Optional[int] = None,
) -> dict[str, Any]:
    return {
        "type": segment_type,
        "start_index": start,
        "end_index": len(field) - 1 if end is None else end,
        "mean_temperature_K": 300.0,
        "temperature_range_K": [300.0, 300.0],
    }


def _symmetric_loop() -> tuple[list[float], list[float]]:
    """
    A loop whose branch crossings are exact by construction.

    The decreasing branch runs from +1000 Oe down to -1000 Oe and brackets
    M = 0 between (+200 Oe, +0.30 emu) and (-200 Oe, -0.10 emu), which
    interpolates to Hc = -100 Oe and Mr = +0.10 emu. The increasing branch is
    the inversion M_inc(H) = -M_dec(-H), giving Hc = +100 Oe and Mr = -0.10 emu.
    Both Hc brackets span 400 Oe.
    """
    decreasing_field = [1000.0, 600.0, 200.0, -200.0, -600.0, -1000.0]
    decreasing_moment = [0.50, 0.45, 0.30, -0.10, -0.45, -0.50]
    increasing_field = [-600.0, -200.0, 200.0, 600.0, 1000.0]
    increasing_moment = [-0.45, -0.30, 0.10, 0.45, 0.50]
    return (
        decreasing_field + increasing_field,
        decreasing_moment + increasing_moment,
    )


def _shift_field(field: list[float], offset: float) -> list[float]:
    return [value + offset for value in field]


class SyntheticCoercivityTests(unittest.TestCase):
    def test_symmetric_loop_has_known_coercive_fields(self) -> None:
        field, moment = _symmetric_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        # Decreasing: Hc = 200 + (0 - 0.30) * (-400) / (-0.40) = -100
        self.assertAlmostEqual(result["Hc_negative_Oe"], -100.0, places=9)
        # Increasing: Hc = -200 + (0 + 0.30) * (400) / (0.40) = +100
        self.assertAlmostEqual(result["Hc_positive_Oe"], 100.0, places=9)

        self.assertAlmostEqual(result["Hc_negative_resolution_Oe"], 400.0, places=9)
        self.assertAlmostEqual(result["Hc_positive_resolution_Oe"], 400.0, places=9)

        negative = result["Hc_negative_bracket"]
        self.assertAlmostEqual(negative["H1_Oe"], 200.0, places=9)
        self.assertAlmostEqual(negative["M1_emu"], 0.30, places=9)
        self.assertAlmostEqual(negative["H2_Oe"], -200.0, places=9)
        self.assertAlmostEqual(negative["M2_emu"], -0.10, places=9)
        self.assertEqual(negative["branch_direction"], "decreasing")
        self.assertEqual(negative["source_index_1"], 2)
        self.assertEqual(negative["source_index_2"], 3)

        positive = result["Hc_positive_bracket"]
        self.assertEqual(positive["branch_direction"], "increasing")
        self.assertEqual(positive["source_index_1"], 7)
        self.assertEqual(positive["source_index_2"], 8)

    def test_loop_asymmetry_is_preserved_not_collapsed(self) -> None:
        field, moment = _symmetric_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertAlmostEqual(result["coercive_center_shift_Oe"], 0.0, places=9)
        self.assertAlmostEqual(result["coercive_half_width_Oe"], 100.0, places=9)
        self.assertIsNotNone(result["Hc_negative_Oe"])
        self.assertIsNotNone(result["Hc_positive_Oe"])
        self.assertNotIn("Hc", result)
        self.assertNotIn("Hc_Oe", result)

    def test_shifted_loop_reports_center_shift(self) -> None:
        field, moment = _symmetric_loop()
        shifted = _shift_field(field, 50.0)
        result = analyze_hysteresis(_parsed(shifted, moment), _segment(shifted))

        self.assertAlmostEqual(result["Hc_negative_Oe"], -50.0, places=9)
        self.assertAlmostEqual(result["Hc_positive_Oe"], 150.0, places=9)
        self.assertAlmostEqual(result["coercive_center_shift_Oe"], 50.0, places=9)
        self.assertAlmostEqual(result["coercive_half_width_Oe"], 100.0, places=9)

    def test_exact_zero_moment_is_not_counted_twice(self) -> None:
        # The decreasing branch passes exactly through M = 0 at H = -100 Oe.
        field = [1000.0, 600.0, 200.0, -100.0, -600.0, -1000.0]
        moment = [0.50, 0.45, 0.30, 0.0, -0.45, -0.50]
        field += [-600.0, -200.0, 200.0, 600.0, 1000.0]
        moment += [-0.45, -0.30, 0.10, 0.45, 0.50]

        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertAlmostEqual(result["Hc_negative_Oe"], -100.0, places=9)
        self.assertEqual(result["Hc_negative_bracket"]["source_index_1"], 2)
        self.assertEqual(result["Hc_negative_bracket"]["source_index_2"], 3)

        duplicate_warnings = [w for w in result["warnings"] if "already recorded" in w]
        self.assertEqual(duplicate_warnings, [])
        multiple_warnings = [w for w in result["warnings"] if "zero-crossings" in w]
        self.assertEqual(multiple_warnings, [])


class SyntheticRemanenceTests(unittest.TestCase):
    def test_known_remanent_moments(self) -> None:
        field, moment = _symmetric_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        # Decreasing: Mr = 0.30 + (0 - 200) * (-0.40) / (-400) = +0.10
        self.assertAlmostEqual(result["Mr_positive_emu"], 0.10, places=9)
        # Increasing: Mr = -0.30 + (0 + 200) * (0.40) / (400) = -0.10
        self.assertAlmostEqual(result["Mr_negative_emu"], -0.10, places=9)

        positive = result["Mr_positive_bracket"]
        self.assertEqual(positive["branch_direction"], "decreasing")
        self.assertEqual(positive["source_index_1"], 2)
        self.assertEqual(positive["source_index_2"], 3)

        negative = result["Mr_negative_bracket"]
        self.assertEqual(negative["branch_direction"], "increasing")
        self.assertEqual(negative["source_index_1"], 7)
        self.assertEqual(negative["source_index_2"], 8)

    def test_remanence_stays_in_emu_without_normalization(self) -> None:
        field, moment = _symmetric_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertEqual(result["units"]["moment"], "emu")
        self.assertEqual(result["units"]["field"], "Oe")
        self.assertEqual(set(result) & FORBIDDEN_KEYS, set())

    def test_wide_square_loop(self) -> None:
        field = [2000.0, 1000.0, 500.0, -500.0, -1000.0, -2000.0]
        moment = [0.60, 0.58, 0.55, 0.45, -0.55, -0.60]
        field += [-1000.0, -500.0, 500.0, 1000.0, 2000.0]
        moment += [-0.58, -0.55, -0.45, 0.55, 0.60]

        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertAlmostEqual(result["Hc_negative_Oe"], -725.0, places=9)
        self.assertAlmostEqual(result["Hc_positive_Oe"], 725.0, places=9)
        self.assertAlmostEqual(result["Mr_positive_emu"], 0.50, places=9)
        self.assertAlmostEqual(result["Mr_negative_emu"], -0.50, places=9)


class MissingCrossingTests(unittest.TestCase):
    def _one_sided_loop(self) -> tuple[list[float], list[float]]:
        # The decreasing branch never reaches negative moment, so it has no Hc.
        field = [1000.0, 500.0, 100.0, -400.0, -1000.0, -400.0, 100.0, 500.0, 1000.0]
        moment = [0.50, 0.45, 0.40, 0.35, 0.30, 0.20, 0.10, -0.10, -0.20]
        return field, moment

    def test_branch_without_moment_crossing_returns_none_and_warns(self) -> None:
        field, moment = self._one_sided_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertIsNone(result["Hc_negative_Oe"])
        self.assertIsNone(result["Hc_negative_bracket"])
        self.assertIsNone(result["Hc_negative_resolution_Oe"])
        self.assertIsNotNone(result["Hc_positive_Oe"])

        self.assertTrue(
            any("negative coercive field" in w for w in result["warnings"]),
            f"Expected a missing-Hc warning, got: {result['warnings']}",
        )

    def test_asymmetry_is_none_when_one_branch_lacks_hc(self) -> None:
        field, moment = self._one_sided_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertIsNone(result["coercive_center_shift_Oe"])
        self.assertIsNone(result["coercive_half_width_Oe"])

    def test_fully_saturated_sweep_has_no_coercivity(self) -> None:
        field = [1000.0, 500.0, 100.0, -500.0, -1000.0, -500.0, 100.0, 500.0, 1000.0]
        moment = [0.50] * 9
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertIsNone(result["Hc_negative_Oe"])
        self.assertIsNone(result["Hc_positive_Oe"])
        self.assertIsNone(result["coercive_half_width_Oe"])
        self.assertTrue(
            any("coercive field" in w for w in result["warnings"]),
            f"Expected missing-Hc warnings, got: {result['warnings']}",
        )


class NonFinitePointTests(unittest.TestCase):
    def test_single_nan_point_is_ignored_with_warning(self) -> None:
        field, moment = _symmetric_loop()
        moment = list(moment)
        moment[1] = float("nan")

        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertEqual(result["point_count"], len(field))
        self.assertEqual(result["valid_point_count"], len(field) - 1)
        self.assertTrue(
            any("non-finite" in w for w in result["warnings"]),
            f"Expected an ignored-point warning, got: {result['warnings']}",
        )
        self.assertAlmostEqual(result["Hc_negative_Oe"], -100.0, places=9)
        self.assertAlmostEqual(result["Hc_positive_Oe"], 100.0, places=9)

    def test_nan_inside_bracket_shifts_to_next_valid_neighbours(self) -> None:
        field, moment = _symmetric_loop()
        moment = list(moment)
        moment[2] = float("nan")

        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        bracket = result["Hc_negative_bracket"]
        self.assertEqual(bracket["source_index_1"], 1)
        self.assertEqual(bracket["source_index_2"], 3)
        self.assertTrue(math.isfinite(bracket["M1_emu"]))
        self.assertTrue(math.isfinite(bracket["M2_emu"]))
        self.assertLess(result["Hc_negative_Oe"], 0.0)

    def test_too_few_valid_points_raises(self) -> None:
        field = [1000.0, float("nan"), float("nan"), -1000.0]
        moment = [0.5, 0.1, -0.1, -0.5]
        with self.assertRaises(HysteresisAnalysisError) as ctx:
            analyze_hysteresis(_parsed(field, moment), _segment(field))
        self.assertIn("valid points", str(ctx.exception))


class ValidationTests(unittest.TestCase):
    def test_rejects_mt_segment(self) -> None:
        field, moment = _symmetric_loop()
        with self.assertRaises(HysteresisAnalysisError) as ctx:
            analyze_hysteresis(
                _parsed(field, moment), _segment(field, segment_type="M-T")
            )
        message = str(ctx.exception)
        self.assertIn("M-H", message)
        self.assertIn("M-T", message)

    def test_rejects_unknown_segment(self) -> None:
        field, moment = _symmetric_loop()
        with self.assertRaises(HysteresisAnalysisError):
            analyze_hysteresis(
                _parsed(field, moment), _segment(field, segment_type="unknown")
            )

    def test_missing_moment_column_raises(self) -> None:
        parsed = {"data": {"Magnetic Field (Oe)": [1.0, 2.0, 3.0, 4.0]}}
        with self.assertRaises(HysteresisAnalysisError) as ctx:
            analyze_hysteresis(parsed, _segment([1.0, 2.0, 3.0, 4.0]))
        self.assertIn("moment", str(ctx.exception).lower())

    def test_unequal_field_and_moment_lengths_raise(self) -> None:
        field, moment = _symmetric_loop()
        parsed = {
            "data": {
                "Magnetic Field (Oe)": field,
                "Moment (emu)": moment[:-2],
            }
        }
        with self.assertRaises(HysteresisAnalysisError) as ctx:
            analyze_hysteresis(parsed, _segment(field))

        message = str(ctx.exception)
        self.assertIn("different lengths", message)
        self.assertIn(str(len(field)), message)
        self.assertIn(str(len(moment) - 2), message)

    def test_negative_start_index_raises(self) -> None:
        field, moment = _symmetric_loop()
        segment = _segment(field)
        segment["start_index"] = -1

        with self.assertRaises(HysteresisAnalysisError) as ctx:
            analyze_hysteresis(_parsed(field, moment), segment)
        self.assertIn("negative", str(ctx.exception))

    def test_end_index_beyond_available_rows_raises(self) -> None:
        field, moment = _symmetric_loop()
        segment = _segment(field)
        segment["end_index"] = len(field)

        with self.assertRaises(HysteresisAnalysisError) as ctx:
            analyze_hysteresis(_parsed(field, moment), segment)

        message = str(ctx.exception)
        self.assertIn("outside the parsed data", message)
        self.assertIn(str(len(field)), message)

    def test_end_index_before_start_index_raises(self) -> None:
        field, moment = _symmetric_loop()
        segment = _segment(field)
        segment["start_index"] = 5
        segment["end_index"] = 2

        with self.assertRaises(HysteresisAnalysisError) as ctx:
            analyze_hysteresis(_parsed(field, moment), segment)
        self.assertIn("before start_index", str(ctx.exception))

    def test_segment_far_outside_data_raises(self) -> None:
        field, moment = _symmetric_loop()
        segment = _segment(field)
        segment["start_index"] = 500
        segment["end_index"] = 600

        with self.assertRaises(HysteresisAnalysisError):
            analyze_hysteresis(_parsed(field, moment), segment)

    def test_full_range_segment_is_accepted(self) -> None:
        field, moment = _symmetric_loop()
        segment = _segment(field)
        segment["start_index"] = 0
        segment["end_index"] = len(field) - 1

        result = analyze_hysteresis(_parsed(field, moment), segment)
        self.assertEqual(result["point_count"], len(field))

    def test_invalid_configuration_rejected(self) -> None:
        for overrides in (
            {"field_direction_tolerance_Oe": -1.0},
            {"minimum_branch_points": 1},
            {"minimum_valid_points": 1},
        ):
            with self.subTest(**overrides):
                with self.assertRaises(HysteresisAnalysisError):
                    HysteresisConfig(**overrides)


class BranchIdentificationTests(unittest.TestCase):
    def test_two_branches_from_loop_starting_at_positive_saturation(self) -> None:
        field, moment = _symmetric_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        directions = [branch["direction"] for branch in result["branches"]]
        self.assertEqual(directions, ["decreasing", "increasing"])
        self.assertEqual(result["branches"][0]["start_index"], 0)
        self.assertEqual(result["branches"][1]["end_index"], len(field) - 1)

    def test_loop_starting_at_negative_saturation(self) -> None:
        field = [-1000.0, -600.0, -200.0, 200.0, 600.0, 1000.0]
        moment = [-0.50, -0.45, -0.30, 0.10, 0.45, 0.50]
        field += [600.0, 200.0, -200.0, -600.0, -1000.0]
        moment += [0.45, 0.30, -0.10, -0.45, -0.50]

        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        directions = [branch["direction"] for branch in result["branches"]]
        self.assertEqual(directions, ["increasing", "decreasing"])
        self.assertAlmostEqual(result["Hc_positive_Oe"], 100.0, places=9)
        self.assertAlmostEqual(result["Hc_negative_Oe"], -100.0, places=9)

    def test_stabilization_steps_do_not_split_a_branch(self) -> None:
        # The 5 Oe wobbles sit under the 50 Oe tolerance and must not start a branch.
        field = [1000.0, 995.0, 600.0, 605.0, 200.0, -200.0, -600.0, -1000.0]
        moment = [0.50, 0.50, 0.45, 0.45, 0.30, -0.10, -0.45, -0.50]
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertEqual(len(result["branches"]), 1)
        self.assertEqual(result["branches"][0]["direction"], "decreasing")
        self.assertEqual(result["branches"][0]["point_count"], len(field))
        self.assertAlmostEqual(result["Hc_negative_Oe"], -100.0, places=9)

    def test_direction_tolerance_is_configurable(self) -> None:
        field = [1000.0, 995.0, 600.0, 605.0, 200.0, -200.0, -600.0, -1000.0]
        moment = [0.50, 0.50, 0.45, 0.45, 0.30, -0.10, -0.45, -0.50]
        parsed = _parsed(field, moment)

        self.assertEqual(len(analyze_hysteresis(parsed, _segment(field))["branches"]), 1)

        sensitive = HysteresisConfig(
            field_direction_tolerance_Oe=1.0, minimum_branch_points=2
        )
        result = analyze_hysteresis(parsed, _segment(field), sensitive)
        self.assertGreater(len(result["branches"]), 1)
        self.assertEqual(result["config"], sensitive)

    def test_short_ramp_region_is_not_forced_into_a_branch(self) -> None:
        # The single-point tail moving the other way is too short to be a branch.
        field = [1000.0, 600.0, 200.0, -200.0, -600.0, -1000.0, -500.0]
        moment = [0.50, 0.45, 0.30, -0.10, -0.45, -0.50, -0.49]
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        self.assertEqual(len(result["branches"]), 1)
        self.assertTrue(
            any("too short" in w for w in result["warnings"]),
            f"Expected a short-run warning, got: {result['warnings']}",
        )

    def test_defaults_reported(self) -> None:
        field, moment = _symmetric_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))
        self.assertEqual(result["config"], DEFAULT_CONFIG)

    def test_data_is_not_sorted_by_field(self) -> None:
        field, moment = _symmetric_loop()
        result = analyze_hysteresis(_parsed(field, moment), _segment(field))

        # A field-sorted analysis could not produce opposite-signed remanence at
        # H = 0, nor opposite-signed coercive fields.
        self.assertLess(result["Mr_negative_emu"], 0.0)
        self.assertGreater(result["Mr_positive_emu"], 0.0)
        self.assertLess(result["Hc_negative_Oe"], 0.0)
        self.assertGreater(result["Hc_positive_Oe"], 0.0)


class RealFe2CoGeHysteresisTests(unittest.TestCase):
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
        cls.result = analyze_hysteresis(cls.parsed, cls.segment)

    def test_segment_is_the_300k_loop(self) -> None:
        self.assertAlmostEqual(self.segment["mean_temperature_K"], 300.0, delta=5.0)
        self.assertEqual(self.result["segment_type"], "M-H")

    def test_two_branches_covering_the_sweep(self) -> None:
        branches = self.result["branches"]
        self.assertEqual(len(branches), 2)
        self.assertEqual(
            [branch["direction"] for branch in branches],
            ["decreasing", "increasing"],
        )
        self.assertEqual(branches[0]["start_index"], self.segment["start_index"])
        self.assertEqual(branches[1]["end_index"], self.segment["end_index"])
        for branch in branches:
            self.assertGreater(branch["point_count"], 50)

        # Branches are disjoint and cover the segment in measurement order.
        self.assertEqual(branches[1]["start_index"], branches[0]["end_index"] + 1)

    def test_coercive_fields_have_correct_sign_structure(self) -> None:
        negative = self.result["Hc_negative_Oe"]
        positive = self.result["Hc_positive_Oe"]

        self.assertIsNotNone(negative)
        self.assertIsNotNone(positive)
        self.assertLess(negative, 0.0)
        self.assertGreater(positive, 0.0)

        # Soft magnet: coercivity is a small fraction of the +/-30 kOe sweep.
        sweep = max(abs(value) for value in self.result["field_range_Oe"])
        self.assertLess(abs(negative), 0.05 * sweep)
        self.assertLess(abs(positive), 0.05 * sweep)

    def test_hc_brackets_come_from_opposite_branches(self) -> None:
        negative = self.result["Hc_negative_bracket"]
        positive = self.result["Hc_positive_bracket"]

        self.assertEqual(negative["branch_direction"], "decreasing")
        self.assertEqual(positive["branch_direction"], "increasing")

        for bracket in (negative, positive):
            self.assertEqual(bracket["source_index_2"], bracket["source_index_1"] + 1)
            self.assertLessEqual(bracket["M1_emu"] * bracket["M2_emu"], 0.0)

        # The interpolated value must lie inside its own bracket.
        self.assertGreater(self.result["Hc_negative_Oe"], negative["H2_Oe"])
        self.assertLess(self.result["Hc_negative_Oe"], negative["H1_Oe"])
        self.assertGreater(self.result["Hc_positive_Oe"], positive["H1_Oe"])
        self.assertLess(self.result["Hc_positive_Oe"], positive["H2_Oe"])

    def test_interpolation_resolution_is_reported_and_realistic(self) -> None:
        for key in ("Hc_negative_resolution_Oe", "Hc_positive_resolution_Oe"):
            resolution = self.result[key]
            self.assertIsNotNone(resolution)
            # Interpolation must not imply precision finer than the field step.
            self.assertGreater(resolution, 100.0)
            self.assertLess(resolution, 2_000.0)

        # Each Hc is smaller than its own bracket spacing here, so the reported
        # resolution is the honest limit on precision.
        self.assertLess(
            abs(self.result["Hc_negative_Oe"]),
            self.result["Hc_negative_resolution_Oe"],
        )

    def test_remanent_moments_have_correct_sign_structure(self) -> None:
        negative = self.result["Mr_negative_emu"]
        positive = self.result["Mr_positive_emu"]

        self.assertIsNotNone(negative)
        self.assertIsNotNone(positive)
        self.assertLess(negative, 0.0)
        self.assertGreater(positive, 0.0)

        # Remanence must be well below the moment reached at full field.
        largest_moment = max(
            abs(self.parsed["data"]["Moment (emu)"][row])
            for row in range(self.segment["start_index"], self.segment["end_index"] + 1)
        )
        self.assertLess(abs(negative), largest_moment)
        self.assertLess(abs(positive), largest_moment)

    def test_mr_brackets_come_from_opposite_branches(self) -> None:
        self.assertEqual(
            self.result["Mr_positive_bracket"]["branch_direction"], "decreasing"
        )
        self.assertEqual(
            self.result["Mr_negative_bracket"]["branch_direction"], "increasing"
        )
        for key in ("Mr_positive_bracket", "Mr_negative_bracket"):
            bracket = self.result[key]
            self.assertLessEqual(bracket["H1_Oe"] * bracket["H2_Oe"], 0.0)

    def test_asymmetry_values_are_derived_and_preserved(self) -> None:
        negative = self.result["Hc_negative_Oe"]
        positive = self.result["Hc_positive_Oe"]

        self.assertAlmostEqual(
            self.result["coercive_center_shift_Oe"],
            (positive + negative) / 2.0,
            places=9,
        )
        self.assertAlmostEqual(
            self.result["coercive_half_width_Oe"],
            (positive - negative) / 2.0,
            places=9,
        )

    def test_no_forbidden_quantities_reported(self) -> None:
        self.assertEqual(set(self.result) & FORBIDDEN_KEYS, set())
        self.assertEqual(self.result["units"]["moment"], "emu")

    def test_report_calculated_values(self) -> None:
        result = self.result
        branches = [
            (b["direction"], b["start_index"], b["end_index"], b["point_count"])
            for b in result["branches"]
        ]
        print(
            "\n".join(
                [
                    "",
                    f"=== Fe2CoGe ~300 K loop: rows {result['start_index']}-"
                    f"{result['end_index']}, T = {result['mean_temperature_K']:.2f} K ===",
                    f"branches                 = {branches}",
                    f"Hc_negative_Oe           = {result['Hc_negative_Oe']:.3f}",
                    f"Hc_positive_Oe           = {result['Hc_positive_Oe']:.3f}",
                    f"Hc_negative_resolution   = {result['Hc_negative_resolution_Oe']:.1f} Oe",
                    f"Hc_positive_resolution   = {result['Hc_positive_resolution_Oe']:.1f} Oe",
                    f"Hc_negative_bracket      = {result['Hc_negative_bracket']}",
                    f"Hc_positive_bracket      = {result['Hc_positive_bracket']}",
                    f"Mr_negative_emu          = {result['Mr_negative_emu']:.6f}",
                    f"Mr_positive_emu          = {result['Mr_positive_emu']:.6f}",
                    f"Mr_negative_bracket      = {result['Mr_negative_bracket']}",
                    f"Mr_positive_bracket      = {result['Mr_positive_bracket']}",
                    f"coercive_center_shift_Oe = {result['coercive_center_shift_Oe']:.3f}",
                    f"coercive_half_width_Oe   = {result['coercive_half_width_Oe']:.3f}",
                    f"warnings                 = {result['warnings']}",
                    "",
                ]
            )
        )
        self.assertTrue(result["branches"])


if __name__ == "__main__":
    unittest.main()
