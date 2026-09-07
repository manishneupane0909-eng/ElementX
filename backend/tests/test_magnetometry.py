import math
import unittest
from pathlib import Path
from typing import Any, Optional

from services.magnetometry import (
    DEFAULT_CONFIG,
    MagnetometrySegmentationError,
    SegmentationConfig,
    segment_measurements,
)
from services.parsers.quantum_design import parse_quantum_design_dat

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

FORBIDDEN_KEYS = {
    "Ms",
    "Mr",
    "Hc",
    "Tc",
    "BHmax",
    "saturation_magnetization",
    "remanence",
    "coercivity",
    "curie_temperature",
}


def _parsed(
    temperature: list[float],
    field: list[float],
    moment: Optional[list[float]] = None,
    timestamps: Optional[list[float]] = None,
    comments: Optional[list[str]] = None,
) -> dict[str, Any]:
    rows = len(temperature)
    data: dict[str, Any] = {
        "Temperature (K)": temperature,
        "Magnetic Field (Oe)": field,
        "Moment (emu)": moment if moment is not None else [0.1] * rows,
    }
    if timestamps is not None:
        data["Time Stamp (sec)"] = timestamps
    if comments is not None:
        data["Comment"] = comments
    return {"data": data}


def _ramp(start: float, stop: float, count: int) -> list[float]:
    if count == 1:
        return [start]
    step = (stop - start) / (count - 1)
    return [start + step * i for i in range(count)]


class RealFileSegmentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        parsed = parse_quantum_design_dat(
            FIXTURE_PATH.read_text(encoding="utf-8", errors="ignore")
        )
        cls.parsed = parsed
        cls.result = segment_measurements(parsed)
        cls.row_count = len(parsed["data"]["Temperature (K)"])

    def test_segments_cover_every_original_row_in_order(self) -> None:
        segments = self.result["segments"]
        self.assertGreater(len(segments), 1)
        self.assertEqual(segments[0]["start_index"], 0)
        self.assertEqual(segments[-1]["end_index"], self.row_count - 1)

        for previous, current in zip(segments, segments[1:]):
            self.assertLessEqual(previous["start_index"], previous["end_index"])
            self.assertEqual(current["start_index"], previous["end_index"] + 1)

        total = sum(segment["point_count"] for segment in segments)
        self.assertEqual(total, self.row_count)

    def test_identifies_one_mt_and_ten_mh_sequences(self) -> None:
        # The file holds a single 1000 Oe temperature ramp followed by field loops
        # at ten distinct setpoints: 55, 85, 100, 150, 200, 250, 265, 300, 350, 360 K.
        types = [segment["type"] for segment in self.result["segments"]]
        self.assertEqual(types.count("M-T"), 1)
        self.assertEqual(types.count("M-H"), 10)
        self.assertEqual(types.count("unknown"), 0)

    def test_mt_segment_spans_full_range_at_constant_field(self) -> None:
        mt_segments = [s for s in self.result["segments"] if s["type"] == "M-T"]
        self.assertEqual(len(mt_segments), 1)
        segment = mt_segments[0]

        low, high = segment["temperature_range_K"]
        self.assertAlmostEqual(low, 55.0, delta=2.0)
        self.assertAlmostEqual(high, 399.0, delta=2.0)

        field_low, field_high = segment["field_range_Oe"]
        self.assertAlmostEqual(field_low, 1000.0, delta=5.0)
        self.assertAlmostEqual(field_high, 1000.0, delta=5.0)
        self.assertAlmostEqual(segment["mean_field_Oe"], 1000.0, delta=5.0)

        self.assertGreater(segment["confidence"], 0.9)

    def test_mh_segments_sit_at_distinct_constant_temperatures(self) -> None:
        mh_segments = [s for s in self.result["segments"] if s["type"] == "M-H"]
        self.assertGreaterEqual(len(mh_segments), 5)

        for segment in mh_segments:
            low, high = segment["temperature_range_K"]
            self.assertLess(
                high - low,
                2.0,
                f"M-H segment at {segment['mean_temperature_K']:.1f} K is not isothermal",
            )
            self.assertGreater(segment["field_range_Oe"][1] - segment["field_range_Oe"][0], 200.0)
            self.assertGreater(segment["confidence"], 0.9)

        means = [segment["mean_temperature_K"] for segment in mh_segments]
        self.assertEqual(means, sorted(means))
        for previous, current in zip(means, means[1:]):
            self.assertGreater(current - previous, 5.0)

    def test_has_mh_segment_near_300k_reaching_30_koe(self) -> None:
        near_300 = [
            segment
            for segment in self.result["segments"]
            if segment["type"] == "M-H"
            and abs(segment["mean_temperature_K"] - 300.0) <= 5.0
        ]
        self.assertEqual(len(near_300), 1)

        low, high = near_300[0]["field_range_Oe"]
        self.assertAlmostEqual(low, -30_000.0, delta=500.0)
        self.assertAlmostEqual(high, 30_000.0, delta=500.0)

    def test_reports_no_magnetic_properties(self) -> None:
        self.assertEqual(set(self.result) & FORBIDDEN_KEYS, set())
        for segment in self.result["segments"]:
            self.assertEqual(set(segment) & FORBIDDEN_KEYS, set())


class SyntheticSegmentationTests(unittest.TestCase):
    def test_clear_mt_data(self) -> None:
        rows = 60
        parsed = _parsed(_ramp(50.0, 300.0, rows), [1000.0] * rows)

        result = segment_measurements(parsed)
        self.assertEqual(len(result["segments"]), 1)

        segment = result["segments"][0]
        self.assertEqual(segment["type"], "M-T")
        self.assertEqual(segment["start_index"], 0)
        self.assertEqual(segment["end_index"], rows - 1)
        self.assertEqual(segment["point_count"], rows)
        self.assertAlmostEqual(segment["temperature_range_K"][0], 50.0, places=6)
        self.assertAlmostEqual(segment["temperature_range_K"][1], 300.0, places=6)
        self.assertGreater(segment["confidence"], 0.9)

    def test_clear_mh_data(self) -> None:
        sweep = _ramp(-30_000.0, 30_000.0, 40) + _ramp(30_000.0, -30_000.0, 40)
        parsed = _parsed([300.0] * len(sweep), sweep)

        result = segment_measurements(parsed)
        self.assertEqual(len(result["segments"]), 1)

        segment = result["segments"][0]
        self.assertEqual(segment["type"], "M-H")
        self.assertAlmostEqual(segment["mean_temperature_K"], 300.0, places=6)
        self.assertAlmostEqual(segment["field_range_Oe"][0], -30_000.0, places=6)
        self.assertAlmostEqual(segment["field_range_Oe"][1], 30_000.0, places=6)
        self.assertGreater(segment["confidence"], 0.9)

    def test_insufficient_variation_is_unknown(self) -> None:
        rows = 30
        parsed = _parsed([300.0] * rows, [1000.0] * rows)

        result = segment_measurements(parsed)
        self.assertEqual(len(result["segments"]), 1)

        segment = result["segments"][0]
        self.assertEqual(segment["type"], "unknown")
        self.assertEqual(segment["confidence"], 0.0)
        self.assertTrue(segment["warnings"])

    def test_simultaneous_sweeps_are_unknown(self) -> None:
        rows = 40
        parsed = _parsed(
            _ramp(50.0, 300.0, rows),
            _ramp(-30_000.0, 30_000.0, rows),
        )

        result = segment_measurements(parsed)
        types = {segment["type"] for segment in result["segments"]}
        self.assertEqual(types, {"unknown"})
        for segment in result["segments"]:
            self.assertEqual(segment["confidence"], 0.0)

    def test_separates_mt_ramp_from_following_mh_loop(self) -> None:
        temperature = _ramp(50.0, 300.0, 40) + [300.0] * 60
        field = [1000.0] * 40 + _ramp(-30_000.0, 30_000.0, 60)
        parsed = _parsed(temperature, field)

        result = segment_measurements(parsed)
        types = [segment["type"] for segment in result["segments"]]
        self.assertEqual(types, ["M-T", "M-H"])
        self.assertEqual(result["segments"][1]["start_index"], 40)

    def test_nan_rows_keep_original_indices(self) -> None:
        temperature = _ramp(50.0, 300.0, 60)
        field = [1000.0] * 60
        temperature[20] = float("nan")
        field[21] = float("nan")

        result = segment_measurements(_parsed(temperature, field))
        segment = result["segments"][0]

        self.assertEqual(segment["type"], "M-T")
        self.assertEqual(segment["start_index"], 0)
        self.assertEqual(segment["end_index"], 59)
        self.assertEqual(segment["point_count"], 60)
        self.assertEqual(segment["valid_point_count"], 58)
        self.assertTrue(math.isfinite(segment["mean_temperature_K"]))
        self.assertTrue(any("non-finite" in w for w in result["warnings"]))

    def test_non_finite_moment_rows_are_retained(self) -> None:
        rows = 40
        moment = [0.1] * rows
        moment[10] = float("nan")

        result = segment_measurements(
            _parsed(_ramp(50.0, 300.0, rows), [1000.0] * rows, moment=moment)
        )
        segment = result["segments"][0]

        self.assertEqual(segment["point_count"], rows)
        self.assertEqual(segment["valid_point_count"], rows)
        self.assertTrue(any("moment" in w for w in result["warnings"]))

    def test_comment_change_creates_boundary(self) -> None:
        rows = 40
        comments = [""] * rows
        comments[20] = "second run"
        parsed = _parsed(
            _ramp(50.0, 300.0, rows),
            [1000.0] * rows,
            comments=comments,
        )

        result = segment_measurements(parsed)
        starts = [segment["start_index"] for segment in result["segments"]]
        self.assertIn(20, starts)
        for segment in result["segments"]:
            self.assertEqual(segment["type"], "M-T")

    def test_timestamps_produce_duration(self) -> None:
        rows = 40
        timestamps = [1000.0 + 30.0 * i for i in range(rows)]
        result = segment_measurements(
            _parsed(_ramp(50.0, 300.0, rows), [1000.0] * rows, timestamps=timestamps)
        )
        self.assertAlmostEqual(result["segments"][0]["duration_sec"], 30.0 * (rows - 1))

    def test_missing_required_column_raises(self) -> None:
        with self.assertRaises(MagnetometrySegmentationError) as ctx:
            segment_measurements({"data": {"Magnetic Field (Oe)": [1.0], "Moment (emu)": [0.1]}})
        self.assertIn("temperature", str(ctx.exception).lower())

    def test_missing_data_key_raises(self) -> None:
        with self.assertRaises(MagnetometrySegmentationError):
            segment_measurements({"columns": ["Temperature (K)"]})


class ColumnLengthValidationTests(unittest.TestCase):
    def _assert_misaligned(self, parsed: dict[str, Any], *lengths: int) -> None:
        with self.assertRaises(MagnetometrySegmentationError) as ctx:
            segment_measurements(parsed)

        message = str(ctx.exception)
        self.assertIn("different lengths", message)
        self.assertIn("Misaligned columns will not be segmented", message)
        for length in lengths:
            self.assertIn(str(length), message)

    def test_temperature_shorter_than_field_and_moment_raises(self) -> None:
        self._assert_misaligned(
            {
                "data": {
                    "Temperature (K)": [300.0, 300.0],
                    "Magnetic Field (Oe)": [1000.0, 1000.0, 1000.0],
                    "Moment (emu)": [0.1, 0.2, 0.3],
                }
            },
            2,
            3,
        )

    def test_field_shorter_than_temperature_and_moment_raises(self) -> None:
        self._assert_misaligned(
            {
                "data": {
                    "Temperature (K)": [300.0, 300.0, 300.0],
                    "Magnetic Field (Oe)": [1000.0, 1000.0],
                    "Moment (emu)": [0.1, 0.2, 0.3],
                }
            },
            3,
            2,
        )

    def test_moment_shorter_than_temperature_and_field_raises(self) -> None:
        self._assert_misaligned(
            {
                "data": {
                    "Temperature (K)": [300.0, 300.0, 300.0],
                    "Magnetic Field (Oe)": [1000.0, 1000.0, 1000.0],
                    "Moment (emu)": [0.1, 0.2],
                }
            },
            3,
            2,
        )


class ConfigurationTests(unittest.TestCase):
    def test_defaults_are_reported_with_the_result(self) -> None:
        result = segment_measurements(_parsed(_ramp(50.0, 300.0, 40), [1000.0] * 40))
        self.assertEqual(result["config"], DEFAULT_CONFIG)

    def test_variation_thresholds_are_configurable(self) -> None:
        rows = 40
        parsed = _parsed(_ramp(300.0, 303.0, rows), [1000.0] * rows)

        self.assertEqual(segment_measurements(parsed)["segments"][0]["type"], "unknown")

        sensitive = SegmentationConfig(
            temperature_noise_tolerance_K=0.1,
            temperature_variation_threshold_K=1.0,
        )
        self.assertEqual(
            segment_measurements(parsed, sensitive)["segments"][0]["type"],
            "M-T",
        )

    def test_setpoint_threshold_controls_loop_splitting(self) -> None:
        sweep = _ramp(-30_000.0, 30_000.0, 30) + _ramp(30_000.0, -30_000.0, 30)
        field = sweep + sweep
        # 3 K apart: below the default setpoint threshold, above the sensitive one.
        temperature = [100.0] * len(sweep) + [103.0] * len(sweep)
        parsed = _parsed(temperature, field)

        merged = segment_measurements(parsed)["segments"]
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["type"], "M-H")

        sensitive = SegmentationConfig(setpoint_change_threshold_K=1.0)
        split = segment_measurements(parsed, sensitive)["segments"]
        self.assertEqual(len(split), 2)
        self.assertEqual([segment["type"] for segment in split], ["M-H", "M-H"])
        self.assertEqual(split[1]["start_index"], len(sweep))
        self.assertAlmostEqual(split[0]["mean_temperature_K"], 100.0, places=6)
        self.assertAlmostEqual(split[1]["mean_temperature_K"], 103.0, places=6)

    def test_merged_loops_with_drifting_temperature_are_unknown(self) -> None:
        sweep = _ramp(-30_000.0, 30_000.0, 30) + _ramp(30_000.0, -30_000.0, 30)
        parsed = _parsed(
            [100.0] * len(sweep) + [130.0] * len(sweep),
            sweep + sweep,
        )

        tolerant = SegmentationConfig(setpoint_change_threshold_K=50.0)
        segments = segment_measurements(parsed, tolerant)["segments"]
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["type"], "unknown")
        self.assertEqual(segments[0]["confidence"], 0.0)

    def test_invalid_configuration_rejected(self) -> None:
        invalid = (
            {"temperature_noise_tolerance_K": 0.0},
            {"field_noise_tolerance_Oe": -1.0},
            {"temperature_variation_threshold_K": 0.0},
            {"field_variation_threshold_Oe": 0.0},
            {"setpoint_change_threshold_K": 0.0},
            {"field_setpoint_change_threshold_Oe": 0.0},
            {"field_setpoint_change_fraction": -0.1},
            {"window_points": 2},
            {"setpoint_confirmation_points": 0},
            {"minimum_segment_points": 0},
        )
        for overrides in invalid:
            with self.subTest(**overrides):
                with self.assertRaises(MagnetometrySegmentationError):
                    SegmentationConfig(**overrides)

    def test_zero_field_setpoint_fraction_allowed(self) -> None:
        config = SegmentationConfig(field_setpoint_change_fraction=0.0)
        result = segment_measurements(_parsed(_ramp(50.0, 300.0, 40), [1000.0] * 40), config)
        self.assertEqual(result["segments"][0]["type"], "M-T")

    def test_config_is_documented_as_heuristic(self) -> None:
        docstring = SegmentationConfig.__doc__ or ""
        self.assertIn("heuristic", docstring.lower())


if __name__ == "__main__":
    unittest.main()
