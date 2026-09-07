import math
import unittest
from pathlib import Path
from typing import Any

from services.magnetometry import segment_measurements
from services.mass_normalization import (
    MassNormalizationError,
    SI_EQUIVALENCE_NOTE,
    normalize_moment_by_mass,
)
from services.parsers.quantum_design import parse_quantum_design_dat
from services.sample_provenance import resolve_sample_mass
from services.saturation import analyze_high_field_magnetization

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


def _authorized_provenance(
    resolved_mass_mg: float = 3.5,
    resolved_source: str = "instrument_header",
    resolution_status: str = "instrument_metadata",
) -> dict[str, Any]:
    return {
        "resolved_mass_mg": resolved_mass_mg,
        "resolved_source": resolved_source,
        "resolution_status": resolution_status,
        "normalization_allowed": True,
    }


class BasicNormalizationTests(unittest.TestCase):
    """TESTS A, B, C: straightforward authorized normalization."""

    def test_positive_moment_is_normalized(self) -> None:
        result = normalize_moment_by_mass(0.45, _authorized_provenance())

        self.assertAlmostEqual(result["specific_magnetization_emu_per_g"], 128.57142857142858)
        self.assertAlmostEqual(result["resolved_mass_mg"], 3.5, places=9)
        self.assertAlmostEqual(result["resolved_mass_g"], 0.0035, places=12)
        self.assertEqual(result["mass_source"], "instrument_header")
        self.assertEqual(result["mass_resolution_status"], "instrument_metadata")
        self.assertEqual(result["input_moment_emu"], 0.45)

    def test_negative_moment_preserves_sign(self) -> None:
        result = normalize_moment_by_mass(-0.45, _authorized_provenance())

        self.assertAlmostEqual(result["specific_magnetization_emu_per_g"], -128.57142857142858)
        self.assertEqual(result["input_moment_emu"], -0.45)

    def test_zero_moment_gives_zero_magnetization(self) -> None:
        result = normalize_moment_by_mass(0.0, _authorized_provenance())

        self.assertEqual(result["specific_magnetization_emu_per_g"], 0.0)
        self.assertEqual(result["specific_magnetization_Am2_per_kg"], 0.0)

    def test_authorized_resolution_statuses_normalize(self) -> None:
        for status, source in (
            ("instrument_metadata", "instrument_header"),
            ("consistent_sources", "instrument_header"),
            ("user_confirmed", "user_confirmed"),
        ):
            with self.subTest(resolution_status=status):
                result = normalize_moment_by_mass(
                    0.45,
                    _authorized_provenance(
                        resolution_status=status, resolved_source=source
                    ),
                )
                self.assertAlmostEqual(
                    result["specific_magnetization_emu_per_g"], 128.57142857142858
                )
                self.assertEqual(result["mass_resolution_status"], status)
                self.assertEqual(result["mass_source"], source)


class ContradictoryProvenanceTests(unittest.TestCase):
    """normalization_allowed=True must not override resolution_status."""

    def _assert_rejected(self, provenance: dict[str, Any], expected_status: str) -> None:
        with self.assertRaises(MassNormalizationError) as ctx:
            normalize_moment_by_mass(0.45, provenance)
        message = str(ctx.exception)
        self.assertIn("resolution_status", message)
        self.assertIn(expected_status, message)

    def test_conflict_status_raises_even_when_allowed(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": 3.5,
                "resolved_source": "instrument_header",
                "resolution_status": "conflict",
            },
            "conflict",
        )

    def test_needs_confirmation_status_raises_even_when_allowed(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": 5.4,
                "resolved_source": "filename",
                "resolution_status": "needs_confirmation",
            },
            "needs_confirmation",
        )

    def test_missing_status_raises_even_when_allowed(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": 3.5,
                "resolved_source": "instrument_header",
                "resolution_status": "missing",
            },
            "missing",
        )

    def test_none_status_raises_even_when_allowed(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": 3.5,
                "resolved_source": "instrument_header",
                "resolution_status": None,
            },
            "unknown",
        )

    def test_non_string_status_raises_even_when_allowed(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": 3.5,
                "resolved_source": "instrument_header",
                "resolution_status": 123,
            },
            "123",
        )

    def test_empty_resolved_source_raises_even_when_allowed(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": 3.5,
                "resolved_source": "",
                "resolution_status": "instrument_metadata",
            },
            "instrument_metadata",
        )


class BlockedProvenanceTests(unittest.TestCase):
    """TESTS D and E: provenance decisions are not overridden."""

    def test_conflict_blocks_normalization(self) -> None:
        provenance = resolve_sample_mass(
            {"metadata": {"SAMPLE_MASS": "3.5"}},
            filename=ORIGINAL_STYLE_FILENAME,
        )
        self.assertFalse(provenance["normalization_allowed"])
        self.assertEqual(provenance["resolution_status"], "conflict")

        with self.assertRaises(MassNormalizationError) as ctx:
            normalize_moment_by_mass(0.45, provenance)

        message = str(ctx.exception)
        self.assertIn("blocked", message)
        self.assertIn("conflict", message)

    def test_filename_only_needs_confirmation(self) -> None:
        provenance = resolve_sample_mass(
            {"metadata": {}}, filename="sample_5p4mg.dat"
        )
        self.assertFalse(provenance["normalization_allowed"])
        self.assertEqual(provenance["resolution_status"], "needs_confirmation")

        with self.assertRaises(MassNormalizationError) as ctx:
            normalize_moment_by_mass(0.45, provenance)

        self.assertIn("needs_confirmation", str(ctx.exception))


class UserConfirmedNormalizationTests(unittest.TestCase):
    """TEST F: user confirmation authorizes normalization."""

    def test_user_confirmed_mass_is_used(self) -> None:
        provenance = resolve_sample_mass(
            {"metadata": {"SAMPLE_MASS": "3.5"}},
            filename=ORIGINAL_STYLE_FILENAME,
            user_confirmed_mass_mg=5.4,
        )
        self.assertTrue(provenance["normalization_allowed"])
        self.assertEqual(provenance["resolution_status"], "user_confirmed")

        result = normalize_moment_by_mass(0.45, provenance)

        self.assertAlmostEqual(result["specific_magnetization_emu_per_g"], 83.33333333333333)
        self.assertEqual(result["mass_source"], "user_confirmed")
        self.assertEqual(result["mass_resolution_status"], "user_confirmed")
        self.assertAlmostEqual(result["resolved_mass_mg"], 5.4, places=9)


class SiEquivalenceTests(unittest.TestCase):
    """TEST G: CGS and SI specific-magnetization values are numerically identical."""

    def test_emu_per_g_equals_am2_per_kg(self) -> None:
        result = normalize_moment_by_mass(0.45, _authorized_provenance())

        self.assertEqual(
            result["specific_magnetization_Am2_per_kg"],
            result["specific_magnetization_emu_per_g"],
        )
        self.assertIn("1 emu/g equals 1 A*m^2/kg", result["si_equivalence_note"])
        self.assertIn("A/m", result["si_equivalence_note"])
        self.assertEqual(result["si_equivalence_note"], SI_EQUIVALENCE_NOTE)

    def test_units_are_reported(self) -> None:
        result = normalize_moment_by_mass(0.45, _authorized_provenance())

        self.assertEqual(
            result["units"],
            {
                "input_moment": "emu",
                "mass": "mg",
                "specific_magnetization_cgs": "emu/g",
                "specific_magnetization_si": "A*m^2/kg",
            },
        )


class InvalidMomentTests(unittest.TestCase):
    """TEST H: invalid moments are rejected."""

    def test_invalid_moments_raise(self) -> None:
        provenance = _authorized_provenance()
        for value in (True, False, "0.45", float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(MassNormalizationError):
                    normalize_moment_by_mass(value, provenance)


class MalformedProvenanceTests(unittest.TestCase):
    """TEST I: malformed provenance is rejected even if authorization is True."""

    def _assert_rejected(self, provenance: dict[str, Any]) -> None:
        with self.assertRaises(MassNormalizationError) as ctx:
            normalize_moment_by_mass(0.45, provenance)
        self.assertIn("resolution_status", str(ctx.exception))

    def test_missing_resolved_mass_raises(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": None,
                "resolved_source": "instrument_header",
                "resolution_status": "instrument_metadata",
            }
        )

    def test_zero_resolved_mass_raises(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": 0.0,
                "resolved_source": "instrument_header",
                "resolution_status": "instrument_metadata",
            }
        )

    def test_negative_resolved_mass_raises(self) -> None:
        self._assert_rejected(
            {
                "normalization_allowed": True,
                "resolved_mass_mg": -3.5,
                "resolved_source": "instrument_header",
                "resolution_status": "instrument_metadata",
            }
        )

    def test_non_finite_resolved_mass_raises(self) -> None:
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                self._assert_rejected(
                    {
                        "normalization_allowed": True,
                        "resolved_mass_mg": value,
                        "resolved_source": "instrument_header",
                        "resolution_status": "instrument_metadata",
                    }
                )

    def test_missing_resolved_source_raises(self) -> None:
        with self.assertRaises(MassNormalizationError) as ctx:
            normalize_moment_by_mass(
                0.45,
                {
                    "normalization_allowed": True,
                    "resolved_mass_mg": 3.5,
                    "resolved_source": None,
                    "resolution_status": "instrument_metadata",
                },
            )
        message = str(ctx.exception)
        self.assertIn("resolved_source", message)
        self.assertIn("instrument_metadata", message)

    def test_non_dict_provenance_raises(self) -> None:
        with self.assertRaises(MassNormalizationError):
            normalize_moment_by_mass(0.45, ["not", "a", "dict"])


class OutputScopeTests(unittest.TestCase):
    def test_no_saturation_or_ms_fields_are_returned(self) -> None:
        result = normalize_moment_by_mass(0.45, _authorized_provenance())
        self.assertEqual(set(result) & FORBIDDEN_KEYS, set())


class RealFe2CoGeNormalizationTests(unittest.TestCase):
    """
    Real-file integration using the ~300 K maximum measured moment.

    The normalized value is a mass-normalized measured moment, not Ms.
    """

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
        cls.saturation = analyze_high_field_magnetization(cls.parsed, cls.segment)
        cls.maximum_measured_moment_emu = cls.saturation[
            "maximum_absolute_measured_moment_emu"
        ]
        cls.conflict_provenance = resolve_sample_mass(
            cls.parsed, filename=ORIGINAL_STYLE_FILENAME
        )
        cls.user_confirmed_provenance = resolve_sample_mass(
            cls.parsed,
            filename=ORIGINAL_STYLE_FILENAME,
            user_confirmed_mass_mg=5.4,
        )

    def test_maximum_measured_moment_is_available(self) -> None:
        self.assertAlmostEqual(
            self.maximum_measured_moment_emu, 0.449183614087668, places=9
        )

    def test_conflict_blocks_normalization_for_real_data(self) -> None:
        self.assertEqual(self.conflict_provenance["resolution_status"], "conflict")
        self.assertFalse(self.conflict_provenance["normalization_allowed"])

        with self.assertRaises(MassNormalizationError) as ctx:
            normalize_moment_by_mass(
                self.maximum_measured_moment_emu, self.conflict_provenance
            )

        self.assertIn("conflict", str(ctx.exception))

    def test_user_confirmed_hypothetical_normalization(self) -> None:
        """
        USER-CONFIRMED / HYPOTHETICAL.

        5.4 mg is supplied only to exercise the normalization path. It is not
        established as the experimentally correct sample mass for this file.
        """
        self.assertTrue(self.user_confirmed_provenance["normalization_allowed"])
        self.assertEqual(
            self.user_confirmed_provenance["resolution_status"], "user_confirmed"
        )
        self.assertAlmostEqual(
            self.user_confirmed_provenance["resolved_mass_mg"], 5.4, places=9
        )

        result = normalize_moment_by_mass(
            self.maximum_measured_moment_emu, self.user_confirmed_provenance
        )

        expected = self.maximum_measured_moment_emu / 0.0054
        self.assertAlmostEqual(result["specific_magnetization_emu_per_g"], expected, places=9)
        self.assertEqual(result["specific_magnetization_Am2_per_kg"], result["specific_magnetization_emu_per_g"])
        self.assertEqual(result["mass_source"], "user_confirmed")
        self.assertEqual(set(result) & FORBIDDEN_KEYS, set())

    def test_report_real_file_results(self) -> None:
        print(
            "\n".join(
                [
                    "",
                    "=== Fe2CoGe ~300 K mass normalization (maximum measured moment) ===",
                    f"maximum_absolute_measured_moment_emu = {self.maximum_measured_moment_emu:.7f}",
                    "",
                    "Conflict path (header 3.5 mg vs filename 5p4mg):",
                    f"  resolution_status     = {self.conflict_provenance['resolution_status']}",
                    f"  normalization_allowed = {self.conflict_provenance['normalization_allowed']}",
                    "  normalize_moment_by_mass -> MassNormalizationError",
                    "",
                    "USER-CONFIRMED / HYPOTHETICAL path (user_confirmed_mass_mg = 5.4):",
                    f"  resolved_mass_mg      = {self.user_confirmed_provenance['resolved_mass_mg']}",
                    f"  resolution_status     = {self.user_confirmed_provenance['resolution_status']}",
                    f"  normalization_allowed = {self.user_confirmed_provenance['normalization_allowed']}",
                    f"  specific_magnetization_emu_per_g = "
                    f"{normalize_moment_by_mass(self.maximum_measured_moment_emu, self.user_confirmed_provenance)['specific_magnetization_emu_per_g']:.6f}",
                    "  (mass-normalized measured moment, NOT Ms)",
                    "",
                ]
            )
        )
        self.assertTrue(math.isfinite(self.maximum_measured_moment_emu))


if __name__ == "__main__":
    unittest.main()
