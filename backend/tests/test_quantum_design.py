import math
import unittest
from pathlib import Path

from services.parsers.quantum_design import (
    QuantumDesignParseError,
    is_quantum_design_dat,
    parse_quantum_design_dat,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)


def _assert_all_finite(test_case: unittest.TestCase, values: list[float], label: str) -> None:
    for idx, value in enumerate(values):
        with test_case.subTest(column=label, row=idx):
            test_case.assertIsInstance(value, float)
            test_case.assertTrue(
                math.isfinite(value),
                f"{label} row {idx} is not finite: {value!r}",
            )


class QuantumDesignParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_text = FIXTURE_PATH.read_text(encoding="utf-8", errors="ignore")

    def test_recognizes_quantum_design_format(self) -> None:
        self.assertTrue(is_quantum_design_dat(self.fixture_text))
        self.assertFalse(is_quantum_design_dat("angle,intensity\n10,100\n"))

    def test_parses_real_fe2coge_file(self) -> None:
        result = parse_quantum_design_dat(self.fixture_text)

        self.assertEqual(result["file_type"], "quantum_design_dat")
        self.assertEqual(
            result["instrument"],
            result["metadata"]["APPNAME"],
        )
        self.assertIn("VersaLab", result["instrument"])
        self.assertIn("VSM", result["instrument"])

        temperature = result["data"]["Temperature (K)"]
        field = result["data"]["Magnetic Field (Oe)"]
        moment = result["data"]["Moment (emu)"]

        self.assertGreater(len(temperature), 100)
        self.assertEqual(len(temperature), len(field))
        self.assertEqual(len(temperature), len(moment))

        _assert_all_finite(self, temperature, "Temperature (K)")
        _assert_all_finite(self, field, "Magnetic Field (Oe)")
        _assert_all_finite(self, moment, "Moment (emu)")

        self.assertAlmostEqual(temperature[0], 55.229, places=2)
        self.assertAlmostEqual(field[0], 1000.019, places=2)
        self.assertAlmostEqual(moment[0], 0.14077, places=4)

        self.assertAlmostEqual(min(temperature), 55.0, delta=1.0)
        self.assertAlmostEqual(max(temperature), 399.0, delta=2.0)
        self.assertAlmostEqual(min(field), -30_000.0, delta=500.0)
        self.assertAlmostEqual(max(field), 30_000.0, delta=500.0)

        self.assertNotAlmostEqual(temperature[0], field[0], places=3)
        self.assertNotAlmostEqual(temperature[0], 3_982_332_483.34, delta=1.0)

        self.assertEqual(result["metadata"].get("SAMPLE_MASS"), "3.5")
        self.assertEqual(result["units"]["Temperature (K)"], "K")
        self.assertEqual(result["units"]["Magnetic Field (Oe)"], "Oe")
        self.assertEqual(result["units"]["Moment (emu)"], "emu")

    def test_comment_column_preserved_as_string(self) -> None:
        result = parse_quantum_design_dat(self.fixture_text)
        comments = result["data"]["Comment"]

        self.assertGreater(len(comments), 0)
        for value in comments[:10]:
            self.assertIsInstance(value, str)
            self.assertNotIsInstance(value, float)

        content = (
            "[Header]\n"
            "INFO,VersaLab VSM Option Release 1.4.6 Build 14,APPNAME\n"
            "[Data]\n"
            "Comment,Temperature (K),Magnetic Field (Oe),Moment (emu)\n"
            "ramp up,55.2,1000,0.14\n"
            ",60.1,2000,0.15\n"
        )
        annotated = parse_quantum_design_dat(content)
        self.assertEqual(annotated["data"]["Comment"][0], "ramp up")
        self.assertEqual(annotated["data"]["Comment"][1], "")
        self.assertIsInstance(annotated["data"]["Temperature (K)"][0], float)

    def test_optional_numeric_columns_remain_numeric(self) -> None:
        result = parse_quantum_design_dat(self.fixture_text)
        timestamps = result["data"]["Time Stamp (sec)"]

        self.assertIsInstance(timestamps[0], float)
        self.assertTrue(math.isfinite(timestamps[0]))

    def test_temperature_is_not_timestamp(self) -> None:
        result = parse_quantum_design_dat(self.fixture_text)
        temperature = result["data"]["Temperature (K)"]
        timestamps = result["data"]["Time Stamp (sec)"]

        _assert_all_finite(self, temperature, "Temperature (K)")

        self.assertLess(max(temperature), 500.0)
        self.assertGreater(min(timestamps), 1_000_000_000.0)

    def test_missing_required_columns_raises(self) -> None:
        malformed = (
            "[Header]\n"
            "INFO,1.0,SAMPLE_MASS\n"
            "[Data]\n"
            "Comment,Time Stamp (sec),Magnetic Field (Oe)\n"
            ",1,1000\n"
        )
        with self.assertRaises(QuantumDesignParseError) as ctx:
            parse_quantum_design_dat(malformed)
        self.assertIn("temperature", str(ctx.exception).lower())

    def test_non_finite_required_values_raise(self) -> None:
        malformed = (
            "[Header]\n"
            "INFO,3.5,SAMPLE_MASS\n"
            "[Data]\n"
            "Comment,Temperature (K),Magnetic Field (Oe),Moment (emu)\n"
            ",not_a_number,1000,0.14\n"
            ",,2000,0.15\n"
            ",nan,3000,invalid\n"
        )
        with self.assertRaises(QuantumDesignParseError) as ctx:
            parse_quantum_design_dat(malformed)
        message = str(ctx.exception).lower()
        self.assertIn("finite", message)

    def test_single_malformed_required_value_warns(self) -> None:
        content = (
            "[Header]\n"
            "INFO,3.5,SAMPLE_MASS\n"
            "[Data]\n"
            "Comment,Temperature (K),Magnetic Field (Oe),Moment (emu)\n"
            ",55.2,1000,0.14\n"
            ",bad_value,2000,0.15\n"
            ",60.1,3000,0.16\n"
        )
        result = parse_quantum_design_dat(content)
        temperature = result["data"]["Temperature (K)"]

        finite_temps = [v for v in temperature if isinstance(v, float) and math.isfinite(v)]
        self.assertEqual(len(finite_temps), 2)
        self.assertTrue(
            any("non-finite" in warning.lower() for warning in result["warnings"]),
            f"Expected non-finite warning, got: {result['warnings']}",
        )
        self.assertAlmostEqual(finite_temps[0], 55.2, places=1)
        self.assertAlmostEqual(finite_temps[1], 60.1, places=1)

    def test_non_quantum_design_file_raises(self) -> None:
        with self.assertRaises(QuantumDesignParseError):
            parse_quantum_design_dat("10 20\n30 40\n")


if __name__ == "__main__":
    unittest.main()
