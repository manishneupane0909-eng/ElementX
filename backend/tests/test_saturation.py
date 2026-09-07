import math
import unittest
from pathlib import Path
from typing import Any, Optional

from services.magnetometry import segment_measurements
from services.parsers.quantum_design import parse_quantum_design_dat
from services.saturation import (
    DEFAULT_CONFIG,
    SaturationAnalysisError,
    SaturationConfig,
    analyze_high_field_magnetization,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

FORBIDDEN_KEYS = {
    "Ms",
    "Ms_emu",
    "estimated_Ms",
    "saturation_magnetization",
    "BHmax",
    "Tc",
    "Tc_K",
    "anisotropy",
    "demagnetization_factor",
    "moment_per_gram",
    "emu_per_gram",
}

FIELD_MAXIMUM = 30_000.0
SATURATION_MOMENT = 0.45


def _loop_fields(field_maximum: float = FIELD_MAXIMUM, step: float = 1500.0) -> list[float]:
    """A full loop: down from +Hmax to -Hmax, then back up to +Hmax."""
    count = int(2 * field_maximum / step)
    descending = [field_maximum - step * index for index in range(count + 1)]
    ascending = [-field_maximum + step * index for index in range(1, count + 1)]
    return descending + ascending


def _one_sided_fields() -> list[float]:
    """
    A loop where only the positive side enters the high-field window.

    The negative extreme stops at -20 kOe, below the 24 kOe threshold, so no
    negative fit is possible while the positive side keeps ten points. The
    extreme is not pushed closer to zero because that would also inflate the
    magnitude asymmetry and confound the one-polarity downgrade under test.
    """
    descending = [
        30_000.0, 28_500.0, 27_000.0, 25_500.0, 24_000.0,
        20_000.0, 15_000.0, 10_000.0, 5_000.0, 0.0,
        -5_000.0, -10_000.0, -15_000.0, -20_000.0,
    ]
    ascending = [
        -15_000.0, -10_000.0, -5_000.0, 0.0, 5_000.0,
        10_000.0, 15_000.0, 20_000.0,
        24_000.0, 25_500.0, 27_000.0, 28_500.0, 30_000.0,
    ]
    return descending + ascending


def _loop_moments(
    fields: list[float],
    susceptibility: float,
    saturation: float = SATURATION_MOMENT,
    width: float = 2_000.0,
    offset: float = 0.0,
) -> list[float]:
    """
    Moment that is flat at high field apart from a linear term.

    ``tanh`` is fully saturated well before the high-field window, so the
    high-field slope is exactly ``susceptibility`` by construction.
    """
    return [
        saturation * math.tanh(value / width) + susceptibility * value + offset
        for value in fields
    ]


def _parsed(fields: list[float], moments: list[float]) -> dict[str, Any]:
    return {
        "data": {
            "Temperature (K)": [300.0] * len(fields),
            "Magnetic Field (Oe)": fields,
            "Moment (emu)": moments,
        }
    }


def _segment(
    fields: list[float],
    segment_type: str = "M-H",
    start: int = 0,
    end: Optional[int] = None,
) -> dict[str, Any]:
    return {
        "type": segment_type,
        "start_index": start,
        "end_index": len(fields) - 1 if end is None else end,
        "mean_temperature_K": 300.0,
    }


def _analyze(
    susceptibility: float,
    offset: float = 0.0,
    config: Optional[SaturationConfig] = None,
) -> dict[str, Any]:
    fields = _loop_fields()
    moments = _loop_moments(fields, susceptibility, offset=offset)
    return analyze_high_field_magnetization(
        _parsed(fields, moments), _segment(fields), config
    )


class NearlySaturatedTests(unittest.TestCase):
    def test_flat_high_field_region_gives_high_quality(self) -> None:
        result = _analyze(susceptibility=1e-7)

        self.assertEqual(result["saturation_evidence_quality"], "high")
        self.assertLess(
            result["positive_relative_high_field_slope"],
            DEFAULT_CONFIG.high_confidence_relative_slope,
        )
        self.assertLess(
            result["negative_relative_high_field_slope"],
            DEFAULT_CONFIG.high_confidence_relative_slope,
        )
        self.assertEqual(result["warnings"], [])

    def test_fitted_slope_matches_construction(self) -> None:
        result = _analyze(susceptibility=1e-7)

        for key in (
            "positive_high_field_slope_emu_per_Oe",
            "negative_high_field_slope_emu_per_Oe",
        ):
            self.assertAlmostEqual(result[key], 1e-7, places=12)

        for key in ("positive_high_field_r_squared", "negative_high_field_r_squared"):
            self.assertAlmostEqual(result[key], 1.0, places=9)

    def test_relative_slope_matches_documented_equation(self) -> None:
        result = _analyze(susceptibility=1e-7)

        slope = result["positive_high_field_slope_emu_per_Oe"]
        field_maximum = max(
            abs(result["maximum_positive_field_Oe"]),
            abs(result["maximum_negative_field_Oe"]),
        )
        expected = abs(slope) * field_maximum / (
            result["maximum_absolute_measured_moment_emu"]
        )
        self.assertAlmostEqual(
            result["positive_relative_high_field_slope"], expected, places=12
        )

    def test_high_field_threshold_follows_fraction(self) -> None:
        result = _analyze(susceptibility=1e-7)
        self.assertAlmostEqual(
            result["high_field_threshold_Oe"],
            DEFAULT_CONFIG.high_field_fraction * FIELD_MAXIMUM,
            places=6,
        )
        self.assertGreaterEqual(
            result["positive_high_field"]["point_count"],
            DEFAULT_CONFIG.minimum_high_field_points,
        )
        self.assertGreaterEqual(
            result["negative_high_field"]["point_count"],
            DEFAULT_CONFIG.minimum_high_field_points,
        )

    def test_maximum_measured_moment_is_not_labelled_ms(self) -> None:
        result = _analyze(susceptibility=1e-7)
        self.assertEqual(set(result) & FORBIDDEN_KEYS, set())
        self.assertIn("maximum_absolute_measured_moment_emu", result)
        self.assertIn("positive_high_field_extrapolated_intercept_emu", result)


class UnsaturatedTests(unittest.TestCase):
    def test_strongly_rising_moment_gives_low_quality(self) -> None:
        result = _analyze(susceptibility=2e-6)

        self.assertEqual(result["saturation_evidence_quality"], "low")
        self.assertGreaterEqual(
            result["positive_relative_high_field_slope"],
            DEFAULT_CONFIG.low_confidence_relative_slope,
        )

    def test_intermediate_slope_gives_medium_quality(self) -> None:
        result = _analyze(susceptibility=5e-7)

        self.assertEqual(result["saturation_evidence_quality"], "medium")
        relative = result["positive_relative_high_field_slope"]
        self.assertGreater(relative, DEFAULT_CONFIG.high_confidence_relative_slope)
        self.assertLess(relative, DEFAULT_CONFIG.low_confidence_relative_slope)

    def test_unsaturated_intercept_is_well_below_maximum_moment(self) -> None:
        result = _analyze(susceptibility=2e-6)

        intercept = result["positive_high_field_extrapolated_intercept_emu"]
        maximum = result["maximum_absolute_measured_moment_emu"]
        self.assertLess(intercept, maximum)
        # The gap is exactly the linear term carried across the sweep.
        self.assertAlmostEqual(maximum - intercept, 2e-6 * FIELD_MAXIMUM, places=6)


class InsufficientHighFieldTests(unittest.TestCase):
    def test_too_few_high_field_points_gives_unknown(self) -> None:
        fields = [30_000.0, 20_000.0, 10_000.0, 0.0, -10_000.0, -20_000.0, -30_000.0]
        fields += [-20_000.0, -10_000.0, 0.0, 10_000.0, 20_000.0, 30_000.0]
        moments = _loop_moments(fields, susceptibility=1e-7)

        result = analyze_high_field_magnetization(
            _parsed(fields, moments), _segment(fields)
        )

        self.assertEqual(result["saturation_evidence_quality"], "unknown")
        self.assertIsNone(result["positive_high_field"])
        self.assertIsNone(result["negative_high_field"])
        self.assertIsNone(result["positive_high_field_slope_emu_per_Oe"])
        self.assertTrue(
            any("high-field points are available" in w for w in result["warnings"]),
            f"Expected an insufficient-points warning, got: {result['warnings']}",
        )
        self.assertTrue(
            any("unknown" in w for w in result["warnings"]),
            f"Expected an unknown-quality warning, got: {result['warnings']}",
        )

    def test_maximum_moment_still_reported_when_quality_unknown(self) -> None:
        fields = [30_000.0, 0.0, -30_000.0, 0.0, 30_000.0]
        moments = _loop_moments(fields, susceptibility=1e-7)

        result = analyze_high_field_magnetization(
            _parsed(fields, moments), _segment(fields)
        )

        self.assertEqual(result["saturation_evidence_quality"], "unknown")
        self.assertGreater(result["maximum_absolute_measured_moment_emu"], 0.0)
        self.assertAlmostEqual(result["maximum_positive_field_Oe"], 30_000.0, places=6)
        self.assertAlmostEqual(result["maximum_negative_field_Oe"], -30_000.0, places=6)

    def test_one_sided_high_field_warns_about_single_polarity(self) -> None:
        fields = _one_sided_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)

        result = analyze_high_field_magnetization(
            _parsed(fields, moments), _segment(fields)
        )

        self.assertIsNotNone(result["positive_high_field"])
        self.assertIsNone(result["negative_high_field"])
        self.assertIsNone(result["relative_slope_disagreement"])
        self.assertTrue(
            any("positive high-field region only" in w for w in result["warnings"]),
            f"Expected a single-polarity warning, got: {result['warnings']}",
        )


class OnePolarityConfidenceTests(unittest.TestCase):
    """
    A single fitted polarity cannot be corroborated by the opposite polarity,
    so it costs one level of evidence quality.
    """

    def _one_sided(
        self, susceptibility: float, config: Optional[SaturationConfig] = None
    ) -> dict[str, Any]:
        fields = _one_sided_fields()
        moments = _loop_moments(fields, susceptibility)
        return analyze_high_field_magnetization(
            _parsed(fields, moments), _segment(fields), config
        )

    def _assert_only_positive_was_fitted(self, result: dict[str, Any]) -> None:
        self.assertIsNotNone(result["positive_high_field"])
        self.assertIsNone(result["negative_high_field"])
        self.assertTrue(
            any("reduced by one level" in w for w in result["warnings"]),
            f"Expected a one-polarity downgrade warning, got: {result['warnings']}",
        )
        # The downgrade under test must be the only one in play.
        self.assertLess(
            result["high_field_magnitude_asymmetry"],
            DEFAULT_CONFIG.maximum_high_field_asymmetry,
        )
        self.assertEqual(
            [w for w in result["warnings"] if "separated by" in w or "disagree by" in w],
            [],
        )

    def test_one_sided_high_becomes_medium(self) -> None:
        two_sided = _analyze(susceptibility=1e-7)
        self.assertEqual(two_sided["saturation_evidence_quality"], "high")

        result = self._one_sided(1e-7)
        self._assert_only_positive_was_fitted(result)
        # Same field maximum and moment scale, so the slope metric is unchanged;
        # only the missing polarity separates this from the two-sided case.
        self.assertAlmostEqual(
            result["positive_relative_high_field_slope"],
            two_sided["positive_relative_high_field_slope"],
            places=12,
        )
        self.assertEqual(result["saturation_evidence_quality"], "medium")

    def test_one_sided_medium_becomes_low(self) -> None:
        two_sided = _analyze(susceptibility=5e-7)
        self.assertEqual(two_sided["saturation_evidence_quality"], "medium")

        result = self._one_sided(5e-7)
        self._assert_only_positive_was_fitted(result)
        self.assertEqual(result["saturation_evidence_quality"], "low")

    def test_one_sided_low_stays_low(self) -> None:
        two_sided = _analyze(susceptibility=2e-6)
        self.assertEqual(two_sided["saturation_evidence_quality"], "low")

        result = self._one_sided(2e-6)
        self._assert_only_positive_was_fitted(result)
        self.assertEqual(result["saturation_evidence_quality"], "low")

    def test_no_usable_polarity_stays_unknown(self) -> None:
        fields = [30_000.0, 20_000.0, 10_000.0, 0.0, -10_000.0, -20_000.0, -30_000.0]
        fields += [-20_000.0, -10_000.0, 0.0, 10_000.0, 20_000.0, 30_000.0]
        moments = _loop_moments(fields, susceptibility=1e-7)

        result = analyze_high_field_magnetization(
            _parsed(fields, moments), _segment(fields)
        )

        self.assertIsNone(result["positive_high_field"])
        self.assertIsNone(result["negative_high_field"])
        self.assertEqual(result["saturation_evidence_quality"], "unknown")
        # 'unknown' is terminal rather than a downgraded level, so the
        # one-polarity rule must not be applied on top of it.
        self.assertEqual(
            [w for w in result["warnings"] if "reduced by one level" in w], []
        )


class AsymmetryTests(unittest.TestCase):
    def test_offset_loop_warns_and_reduces_confidence(self) -> None:
        symmetric = _analyze(susceptibility=1e-7)
        self.assertEqual(symmetric["saturation_evidence_quality"], "high")

        offset = _analyze(susceptibility=1e-7, offset=0.05)

        self.assertGreater(
            offset["high_field_magnitude_asymmetry"],
            DEFAULT_CONFIG.maximum_high_field_asymmetry,
        )
        self.assertTrue(
            any("field extremes differ by" in w for w in offset["warnings"]),
            f"Expected an asymmetry warning, got: {offset['warnings']}",
        )
        self.assertEqual(offset["saturation_evidence_quality"], "medium")

    def test_asymmetry_matches_definition(self) -> None:
        result = _analyze(susceptibility=1e-7, offset=0.05)

        positive = abs(result["moment_at_max_positive_field_emu"])
        negative = abs(result["moment_at_max_negative_field_emu"])
        expected = abs(positive - negative) / ((positive + negative) / 2.0)
        self.assertAlmostEqual(
            result["high_field_magnitude_asymmetry"], expected, places=12
        )

    def test_data_is_not_corrected_for_asymmetry(self) -> None:
        result = _analyze(susceptibility=1e-7, offset=0.05)

        # The offset must survive into the reported extremes untouched.
        self.assertGreater(
            abs(result["moment_at_max_positive_field_emu"]),
            abs(result["moment_at_max_negative_field_emu"]),
        )

    def test_symmetric_loop_has_negligible_asymmetry(self) -> None:
        result = _analyze(susceptibility=1e-7)
        self.assertLess(result["high_field_magnitude_asymmetry"], 1e-9)


class BranchSeparationTests(unittest.TestCase):
    def _separated_branches(self) -> tuple[list[float], list[float]]:
        """Branches offset by 0.03 emu at high field, far above the 1% tolerance."""
        fields = _loop_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)
        turning_point = fields.index(-FIELD_MAXIMUM)
        moments = [
            value if index <= turning_point else value - 0.03
            for index, value in enumerate(moments)
        ]
        return fields, moments

    def test_separated_branches_warn_and_reduce_confidence(self) -> None:
        fields, moments = self._separated_branches()
        result = analyze_high_field_magnetization(
            _parsed(fields, moments), _segment(fields)
        )

        separation = result["positive_high_field"]["branch_separation"]
        self.assertIsNotNone(separation)
        self.assertGreater(
            separation, DEFAULT_CONFIG.maximum_high_field_branch_separation
        )
        self.assertTrue(
            any("branches" in w and "separated by" in w for w in result["warnings"]),
            f"Expected a branch-separation warning, got: {result['warnings']}",
        )
        self.assertNotEqual(result["saturation_evidence_quality"], "high")

    def test_agreeing_branches_produce_no_warning(self) -> None:
        result = _analyze(susceptibility=1e-7)

        separation = result["positive_high_field"]["branch_separation"]
        self.assertIsNotNone(separation)
        self.assertLess(
            separation, DEFAULT_CONFIG.maximum_high_field_branch_separation
        )
        self.assertEqual(
            [w for w in result["warnings"] if "separated by" in w],
            [],
        )


class NonFinitePointTests(unittest.TestCase):
    def test_nan_in_high_field_region_is_ignored_with_warning(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)
        baseline = analyze_high_field_magnetization(
            _parsed(fields, moments), _segment(fields)
        )

        moments = list(moments)
        moments[2] = float("nan")
        result = analyze_high_field_magnetization(
            _parsed(fields, moments), _segment(fields)
        )

        self.assertEqual(result["point_count"], len(fields))
        self.assertEqual(result["valid_point_count"], len(fields) - 1)
        self.assertTrue(
            any("non-finite" in w for w in result["warnings"]),
            f"Expected an ignored-point warning, got: {result['warnings']}",
        )

        self.assertEqual(
            result["positive_high_field"]["point_count"],
            baseline["positive_high_field"]["point_count"] - 1,
        )
        self.assertEqual(result["saturation_evidence_quality"], "high")
        self.assertAlmostEqual(
            result["positive_high_field_slope_emu_per_Oe"], 1e-7, places=12
        )

    def test_too_few_valid_points_raises(self) -> None:
        fields = [30_000.0, float("nan"), -30_000.0]
        moments = [0.45, 0.0, float("nan")]
        with self.assertRaises(SaturationAnalysisError) as ctx:
            analyze_high_field_magnetization(
                _parsed(fields, moments), _segment(fields)
            )
        self.assertIn("valid points", str(ctx.exception))


class ValidationTests(unittest.TestCase):
    def test_rejects_mt_segment(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)
        with self.assertRaises(SaturationAnalysisError) as ctx:
            analyze_high_field_magnetization(
                _parsed(fields, moments), _segment(fields, segment_type="M-T")
            )
        message = str(ctx.exception)
        self.assertIn("M-H", message)
        self.assertIn("M-T", message)

    def test_rejects_unknown_segment(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)
        with self.assertRaises(SaturationAnalysisError):
            analyze_high_field_magnetization(
                _parsed(fields, moments), _segment(fields, segment_type="unknown")
            )

    def test_unequal_field_and_moment_lengths_raise(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)
        parsed = {
            "data": {
                "Magnetic Field (Oe)": fields,
                "Moment (emu)": moments[:-3],
            }
        }
        with self.assertRaises(SaturationAnalysisError) as ctx:
            analyze_high_field_magnetization(parsed, _segment(fields))

        message = str(ctx.exception)
        self.assertIn("different lengths", message)
        self.assertIn(str(len(fields)), message)
        self.assertIn(str(len(moments) - 3), message)

    def test_missing_moment_column_raises(self) -> None:
        parsed = {"data": {"Magnetic Field (Oe)": [1.0, 2.0, 3.0]}}
        with self.assertRaises(SaturationAnalysisError) as ctx:
            analyze_high_field_magnetization(parsed, _segment([1.0, 2.0, 3.0]))
        self.assertIn("moment", str(ctx.exception).lower())

    def test_negative_start_index_raises(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)
        segment = _segment(fields)
        segment["start_index"] = -1

        with self.assertRaises(SaturationAnalysisError) as ctx:
            analyze_high_field_magnetization(_parsed(fields, moments), segment)
        self.assertIn("negative", str(ctx.exception))

    def test_end_index_beyond_available_rows_raises(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)
        segment = _segment(fields)
        segment["end_index"] = len(fields)

        with self.assertRaises(SaturationAnalysisError) as ctx:
            analyze_high_field_magnetization(_parsed(fields, moments), segment)
        self.assertIn("outside the parsed data", str(ctx.exception))

    def test_end_index_before_start_index_raises(self) -> None:
        fields = _loop_fields()
        moments = _loop_moments(fields, susceptibility=1e-7)
        segment = _segment(fields)
        segment["start_index"] = 10
        segment["end_index"] = 4

        with self.assertRaises(SaturationAnalysisError) as ctx:
            analyze_high_field_magnetization(_parsed(fields, moments), segment)
        self.assertIn("before start_index", str(ctx.exception))

    def test_invalid_configuration_rejected(self) -> None:
        for overrides in (
            {"high_field_fraction": 0.0},
            {"high_field_fraction": 1.0},
            {"high_field_fraction": 1.5},
            {"minimum_high_field_points": 1},
            {"high_confidence_relative_slope": 0.0},
            {"low_confidence_relative_slope": 0.01},
            {"maximum_relative_slope_disagreement": 0.0},
            {"maximum_high_field_asymmetry": 0.0},
            {"maximum_high_field_branch_separation": 0.0},
            {"branch_direction_tolerance_Oe": -1.0},
        ):
            with self.subTest(**overrides):
                with self.assertRaises(SaturationAnalysisError):
                    SaturationConfig(**overrides)

    def test_config_documented_as_heuristic(self) -> None:
        docstring = SaturationConfig.__doc__ or ""
        self.assertIn("heuristic", docstring.lower())
        self.assertIn("not a physical", docstring.lower())


class ConfigurationTests(unittest.TestCase):
    def test_defaults_reported(self) -> None:
        result = _analyze(susceptibility=1e-7)
        self.assertEqual(result["config"], DEFAULT_CONFIG)
        self.assertAlmostEqual(DEFAULT_CONFIG.high_field_fraction, 0.80, places=9)
        self.assertAlmostEqual(
            DEFAULT_CONFIG.high_confidence_relative_slope, 0.02, places=9
        )
        self.assertAlmostEqual(
            DEFAULT_CONFIG.low_confidence_relative_slope, 0.10, places=9
        )

    def test_high_field_fraction_changes_point_counts(self) -> None:
        narrow = SaturationConfig(high_field_fraction=0.9)
        wide = SaturationConfig(high_field_fraction=0.7)

        narrow_result = _analyze(susceptibility=1e-7, config=narrow)
        wide_result = _analyze(susceptibility=1e-7, config=wide)

        self.assertLess(
            narrow_result["positive_high_field"]["point_count"],
            wide_result["positive_high_field"]["point_count"],
        )
        self.assertGreater(
            wide_result["high_field_threshold_Oe"],
            0.5 * FIELD_MAXIMUM,
        )

    def test_stricter_quality_threshold_downgrades(self) -> None:
        strict = SaturationConfig(
            high_confidence_relative_slope=0.001,
            low_confidence_relative_slope=0.005,
        )
        result = _analyze(susceptibility=1e-7, config=strict)
        self.assertEqual(result["saturation_evidence_quality"], "low")


class RealFe2CoGeSaturationTests(unittest.TestCase):
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
        cls.result = analyze_high_field_magnetization(cls.parsed, cls.segment)

    def test_segment_is_the_300k_loop(self) -> None:
        self.assertAlmostEqual(self.segment["mean_temperature_K"], 300.0, delta=5.0)
        self.assertEqual(self.result["segment_type"], "M-H")

    def test_field_extremes_reach_30_koe(self) -> None:
        self.assertAlmostEqual(
            self.result["maximum_positive_field_Oe"], 30_000.0, delta=500.0
        )
        self.assertAlmostEqual(
            self.result["maximum_negative_field_Oe"], -30_000.0, delta=500.0
        )

    def test_moments_at_extremes_are_opposite_and_symmetric(self) -> None:
        positive = self.result["moment_at_max_positive_field_emu"]
        negative = self.result["moment_at_max_negative_field_emu"]

        self.assertGreater(positive, 0.0)
        self.assertLess(negative, 0.0)
        self.assertLess(
            self.result["high_field_magnitude_asymmetry"],
            DEFAULT_CONFIG.maximum_high_field_asymmetry,
        )

    def test_high_field_threshold_and_point_counts(self) -> None:
        field_maximum = max(
            abs(self.result["maximum_positive_field_Oe"]),
            abs(self.result["maximum_negative_field_Oe"]),
        )
        self.assertAlmostEqual(
            self.result["high_field_threshold_Oe"],
            0.80 * field_maximum,
            places=6,
        )
        self.assertGreater(self.result["positive_high_field"]["point_count"], 20)
        self.assertGreater(self.result["negative_high_field"]["point_count"], 20)

    def test_high_field_slope_is_small_but_systematic(self) -> None:
        for key in (
            "positive_relative_high_field_slope",
            "negative_relative_high_field_slope",
        ):
            relative = self.result[key]
            self.assertGreater(relative, 0.0)
            self.assertLess(relative, DEFAULT_CONFIG.high_confidence_relative_slope)

        # A high R^2 means the residual rise is a real trend, not scatter, so the
        # moment is still genuinely climbing at the highest measured fields.
        for key in ("positive_high_field_r_squared", "negative_high_field_r_squared"):
            self.assertGreater(self.result[key], 0.9)

    def test_both_polarities_agree(self) -> None:
        self.assertLess(
            self.result["relative_slope_disagreement"],
            DEFAULT_CONFIG.maximum_relative_slope_disagreement,
        )
        for side in ("positive_high_field", "negative_high_field"):
            separation = self.result[side]["branch_separation"]
            self.assertIsNotNone(separation)
            self.assertLess(
                separation, DEFAULT_CONFIG.maximum_high_field_branch_separation
            )

    def test_saturation_evidence_quality_is_high_for_this_loop(self) -> None:
        self.assertEqual(self.result["saturation_evidence_quality"], "high")
        self.assertEqual(self.result["warnings"], [])

    def test_linear_intercept_differs_from_maximum_measured_moment(self) -> None:
        maximum = self.result["maximum_absolute_measured_moment_emu"]
        intercept = self.result["positive_high_field_extrapolated_intercept_emu"]

        self.assertLess(intercept, maximum)
        gap = (maximum - intercept) / maximum
        # The two candidate definitions of "saturation" disagree at the sub-percent
        # level, which is why neither is reported as Ms.
        self.assertAlmostEqual(gap, 0.0073, delta=0.002)

    def test_no_ms_is_reported(self) -> None:
        self.assertEqual(set(self.result) & FORBIDDEN_KEYS, set())
        for side in ("positive_high_field", "negative_high_field"):
            self.assertEqual(set(self.result[side]) & FORBIDDEN_KEYS, set())
        self.assertEqual(self.result["units"]["moment"], "emu")

    def test_report_calculated_values(self) -> None:
        result = self.result
        positive = result["positive_high_field"]
        negative = result["negative_high_field"]
        print(
            "\n".join(
                [
                    "",
                    "=== Fe2CoGe ~300 K high-field diagnostics: rows "
                    f"{result['start_index']}-{result['end_index']}, "
                    f"T = {result['mean_temperature_K']:.2f} K ===",
                    f"maximum_positive_field_Oe            = {result['maximum_positive_field_Oe']:.1f}",
                    f"maximum_negative_field_Oe            = {result['maximum_negative_field_Oe']:.1f}",
                    f"moment_at_max_positive_field_emu     = {result['moment_at_max_positive_field_emu']:.7f}",
                    f"moment_at_max_negative_field_emu     = {result['moment_at_max_negative_field_emu']:.7f}",
                    f"maximum_absolute_measured_moment_emu = {result['maximum_absolute_measured_moment_emu']:.7f}",
                    f"high_field_threshold_Oe              = {result['high_field_threshold_Oe']:.1f}",
                    "",
                    f"positive: n={positive['point_count']}  "
                    f"slope={positive['slope_emu_per_Oe']:.6e} emu/Oe  "
                    f"intercept={positive['extrapolated_intercept_emu']:.7f} emu  "
                    f"R2={positive['r_squared']:.4f}  "
                    f"relative_slope={positive['relative_slope']:.5f}  "
                    f"branch_separation={positive['branch_separation']:.2e}",
                    f"negative: n={negative['point_count']}  "
                    f"slope={negative['slope_emu_per_Oe']:.6e} emu/Oe  "
                    f"intercept={negative['extrapolated_intercept_emu']:.7f} emu  "
                    f"R2={negative['r_squared']:.4f}  "
                    f"relative_slope={negative['relative_slope']:.5f}  "
                    f"branch_separation={negative['branch_separation']:.2e}",
                    "",
                    f"relative_slope_disagreement          = {result['relative_slope_disagreement']:.4f}",
                    f"high_field_magnitude_asymmetry       = {result['high_field_magnitude_asymmetry']:.3e}",
                    f"saturation_evidence_quality          = {result['saturation_evidence_quality']}",
                    f"warnings                             = {result['warnings']}",
                    "",
                ]
            )
        )
        self.assertIsNotNone(result["saturation_evidence_quality"])


if __name__ == "__main__":
    unittest.main()
