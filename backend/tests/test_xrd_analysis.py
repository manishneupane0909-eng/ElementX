from __future__ import annotations

import math
import unittest
from pathlib import Path

from services.xrd_analysis import (
    XRD_PIPELINE_VERSION,
    InvalidXrdUploadError,
    analyze_xrd_bytes,
    parse_xrd_text,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "two_column_xrd_test.xy"
QD_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)


class XrdParserTests(unittest.TestCase):
    def test_whitespace_two_column_preserves_order(self) -> None:
        text = "21.5  3\n20.0  1\n20.1  2\n"
        two_theta, intensity, warnings = parse_xrd_text(text)

        self.assertEqual(two_theta, [21.5, 20.0, 20.1])
        self.assertEqual(intensity, [3.0, 1.0, 2.0])
        self.assertEqual(warnings, [])

    def test_csv_two_column(self) -> None:
        text = "20.0,10\n20.1,12\n20.2,11\n20.3,13\n20.4,9\n"
        two_theta, intensity, warnings = parse_xrd_text(text)

        self.assertEqual(two_theta, [20.0, 20.1, 20.2, 20.3, 20.4])
        self.assertEqual(intensity, [10.0, 12.0, 11.0, 13.0, 9.0])
        self.assertEqual(warnings, [])

    def test_comments_and_header_are_skipped(self) -> None:
        text = (
            "# comment\n"
            "2theta intensity\n"
            "; also a comment\n"
            "20.0 10\n"
            "20.1 12\n"
            "20.2 11\n"
            "20.3 13\n"
            "20.4 9\n"
        )
        two_theta, intensity, warnings = parse_xrd_text(text)

        self.assertEqual(len(two_theta), 5)
        self.assertEqual(two_theta[0], 20.0)
        self.assertEqual(warnings, [])

    def test_non_numeric_lines_are_skipped_with_warning(self) -> None:
        text = "20.0 10\nabc def\n20.1 12\n20.2 11\n20.3 13\n20.4 9\n"
        two_theta, intensity, warnings = parse_xrd_text(text)

        self.assertEqual(len(two_theta), 5)
        self.assertEqual(len(intensity), 5)
        self.assertTrue(any("skipped" in warning for warning in warnings))

    def test_extra_columns_warn_and_keep_first_two(self) -> None:
        text = "20.0 10 999\n20.1 12 888\n20.2 11 1\n20.3 13 2\n20.4 9 3\n"
        two_theta, intensity, warnings = parse_xrd_text(text)

        self.assertEqual(two_theta, [20.0, 20.1, 20.2, 20.3, 20.4])
        self.assertEqual(intensity, [10.0, 12.0, 11.0, 13.0, 9.0])
        self.assertTrue(any("more than two columns" in warning for warning in warnings))

    def test_non_finite_values_are_skipped(self) -> None:
        text = "20.0 10\n20.1 nan\ninf 12\n20.2 11\n20.3 13\n20.4 9\n20.5 8\n"
        two_theta, intensity, warnings = parse_xrd_text(text)

        self.assertTrue(all(math.isfinite(value) for value in two_theta))
        self.assertTrue(all(math.isfinite(value) for value in intensity))
        self.assertEqual(len(two_theta), len(intensity))
        self.assertGreaterEqual(len(two_theta), 5)


class XrdAnalysisTests(unittest.TestCase):
    def test_fixture_analysis_summary_and_version(self) -> None:
        result = analyze_xrd_bytes(FIXTURE_PATH.read_bytes(), FIXTURE_PATH.name)

        self.assertEqual(result["analysis_version"], XRD_PIPELINE_VERSION)
        self.assertEqual(result["file"]["format"], "two_column_xrd_text")
        self.assertEqual(result["file"]["filename"], FIXTURE_PATH.name)
        self.assertEqual(result["summary"]["point_count"], 40)
        self.assertEqual(result["summary"]["two_theta_min_deg"], 20.0)
        self.assertEqual(result["summary"]["two_theta_max_deg"], 23.9)
        self.assertEqual(result["summary"]["intensity_min"], 10.0)
        self.assertEqual(result["summary"]["intensity_max"], 100.0)
        self.assertEqual(
            len(result["series"]["two_theta_deg"]),
            len(result["series"]["intensity"]),
        )
        self.assertEqual(result["series"]["two_theta_deg"][0], 20.0)
        self.assertEqual(result["series"]["two_theta_deg"][-1], 23.9)
        self.assertEqual(
            result["peak_detection"]["label"],
            "candidate_intensity_maxima",
        )
        self.assertNotIn("hkl", result)
        self.assertNotIn("phase", result)
        peak_angles = [peak["two_theta_deg"] for peak in result["peaks"]]
        self.assertIn(21.0, peak_angles)
        self.assertIn(22.5, peak_angles)

    def test_too_few_points_are_rejected(self) -> None:
        content = b"20.0 1\n20.1 2\n20.2 3\n20.3 4\n"
        with self.assertRaises(InvalidXrdUploadError) as ctx:
            analyze_xrd_bytes(content, "too_few.xy")
        self.assertIn("too few", str(ctx.exception))

    def test_empty_two_theta_range_is_rejected(self) -> None:
        content = b"20.0 1\n20.0 2\n20.0 3\n20.0 4\n20.0 5\n"
        with self.assertRaises(InvalidXrdUploadError) as ctx:
            analyze_xrd_bytes(content, "flat.xy")
        self.assertIn("2θ range is empty", str(ctx.exception))

    def test_quantum_design_dat_is_rejected_as_xrd(self) -> None:
        with self.assertRaises(InvalidXrdUploadError) as ctx:
            analyze_xrd_bytes(QD_FIXTURE_PATH.read_bytes(), QD_FIXTURE_PATH.name)
        self.assertIn("Quantum Design", str(ctx.exception))

    def test_unsupported_extension_is_rejected(self) -> None:
        with self.assertRaises(InvalidXrdUploadError) as ctx:
            analyze_xrd_bytes(b"20.0 1\n20.1 2\n20.2 3\n20.3 4\n20.4 5\n", "scan.ras")
        self.assertIn("Unsupported XRD file type", str(ctx.exception))

    def test_invalid_utf8_is_rejected(self) -> None:
        with self.assertRaises(InvalidXrdUploadError) as ctx:
            analyze_xrd_bytes(b"\xff\xfe20.0 1", "bad.xy")
        self.assertIn("UTF-8", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
