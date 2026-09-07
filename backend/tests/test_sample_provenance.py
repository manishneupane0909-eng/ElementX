import unittest
from pathlib import Path
from typing import Any, Optional

from services.parsers.quantum_design import parse_quantum_design_dat
from services.sample_provenance import (
    DEFAULT_CONFIG,
    SampleProvenanceConfig,
    SampleProvenanceError,
    resolve_sample_mass,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat"
)

ORIGINAL_STYLE_FILENAME = "Fe2CoGe_annealed_5p4mg_48HRS_900C.dat"

FORBIDDEN_KEYS = {
    "emu_per_gram",
    "moment_per_gram",
    "magnetization_emu_per_g",
    "Am2_per_kg",
    "bohr_magnetons_per_formula_unit",
    "Ms",
    "Ms_emu",
    "BHmax",
    "normalized_moment",
}


def _parsed(metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "data": {"Moment (emu)": [0.1, 0.2]},
        "metadata": {} if metadata is None else metadata,
    }
    return parsed


def _candidates_by_source(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Only safe where at most one candidate per source is expected."""
    return {
        candidate["source"]: candidate for candidate in result["mass_candidates"]
    }


def _filename_candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in result["mass_candidates"]
        if candidate["source"] == "filename"
    ]


def _candidate_values(result: dict[str, Any], source: str) -> list[float]:
    return [
        candidate["value_mg"]
        for candidate in result["mass_candidates"]
        if candidate["source"] == source
    ]


class InstrumentHeaderTests(unittest.TestCase):
    """TEST A: a valid Quantum Design header mass."""

    def test_valid_header_mass_is_used(self) -> None:
        result = resolve_sample_mass(_parsed({"SAMPLE_MASS": "3.5"}))

        self.assertEqual(len(result["mass_candidates"]), 1)
        candidate = result["mass_candidates"][0]
        self.assertAlmostEqual(candidate["value_mg"], 3.5, places=9)
        self.assertEqual(candidate["source"], "instrument_header")
        self.assertEqual(candidate["source_key"], "SAMPLE_MASS")

        self.assertAlmostEqual(result["resolved_mass_mg"], 3.5, places=9)
        self.assertEqual(result["resolved_source"], "instrument_header")
        self.assertEqual(result["resolution_status"], "instrument_metadata")
        self.assertTrue(result["normalization_allowed"])
        self.assertEqual(result["warnings"], [])

    def test_raw_string_is_preserved_alongside_interpreted_value(self) -> None:
        result = resolve_sample_mass(_parsed({"SAMPLE_MASS": "3.5"}))
        candidate = result["mass_candidates"][0]

        self.assertEqual(candidate["raw_value"], "3.5")
        self.assertIsInstance(candidate["raw_value"], str)
        self.assertIsInstance(candidate["value_mg"], float)
        self.assertEqual(result["units"]["mass"], "mg")
        self.assertIn("milligram", result["instrument_mass_unit_assumption"])

    def test_numeric_header_mass_is_accepted(self) -> None:
        result = resolve_sample_mass(_parsed({"SAMPLE_MASS": 3.5}))
        self.assertAlmostEqual(result["resolved_mass_mg"], 3.5, places=9)
        self.assertEqual(result["resolution_status"], "instrument_metadata")

    def test_parser_metadata_is_not_modified(self) -> None:
        metadata = {"SAMPLE_MASS": "3.5", "SAMPLE_MATERIAL": "Fe2CoGe"}
        parsed = _parsed(metadata)
        resolve_sample_mass(parsed, filename=ORIGINAL_STYLE_FILENAME)

        self.assertEqual(metadata, {"SAMPLE_MASS": "3.5", "SAMPLE_MATERIAL": "Fe2CoGe"})
        self.assertIs(parsed["metadata"], metadata)

    def test_absent_key_means_missing_not_invalid(self) -> None:
        result = resolve_sample_mass(_parsed({"SAMPLE_MATERIAL": "Fe2CoGe"}))

        self.assertEqual(result["mass_candidates"], [])
        self.assertEqual(result["rejected_candidates"], [])
        self.assertEqual(result["resolution_status"], "missing")
        self.assertFalse(result["normalization_allowed"])

    def test_empty_header_value_is_treated_as_absent(self) -> None:
        # Quantum Design writes empty INFO fields routinely.
        result = resolve_sample_mass(_parsed({"SAMPLE_MASS": "   "}))

        self.assertEqual(result["resolution_status"], "missing")
        self.assertEqual(result["rejected_candidates"], [])


class FilenameHintTests(unittest.TestCase):
    """TESTS B, C, D: explicit mg tokens only."""

    def _filename_candidate(self, filename: str) -> Optional[dict[str, Any]]:
        result = resolve_sample_mass(_parsed(), filename=filename)
        return _candidates_by_source(result).get("filename")

    def test_p_notation_token_is_parsed(self) -> None:
        candidate = self._filename_candidate("Fe2CoGe_5p4mg_48HRS_900C.dat")

        self.assertIsNotNone(candidate)
        self.assertAlmostEqual(candidate["value_mg"], 5.4, places=9)
        self.assertEqual(candidate["raw_value"], "5p4mg")
        self.assertEqual(candidate["source"], "filename")

    def test_anneal_and_temperature_tokens_are_ignored(self) -> None:
        candidate = self._filename_candidate("Fe2CoGe_5p4mg_48HRS_900C.dat")

        self.assertEqual(candidate["matched_tokens"], ["5p4mg"])
        for ignored in (48.0, 900.0, 2.0):
            self.assertNotAlmostEqual(candidate["value_mg"], ignored, places=6)

    def test_decimal_point_token_is_parsed(self) -> None:
        candidate = self._filename_candidate("sample_5.4mg.dat")

        self.assertIsNotNone(candidate)
        self.assertAlmostEqual(candidate["value_mg"], 5.4, places=9)
        self.assertEqual(candidate["raw_value"], "5.4mg")

    def test_number_without_mg_unit_is_not_a_mass(self) -> None:
        result = resolve_sample_mass(_parsed(), filename="Fe2CoGe_5p4_900C.dat")

        self.assertEqual(result["mass_candidates"], [])
        self.assertEqual(result["resolution_status"], "missing")

    def test_bare_numbers_are_never_masses(self) -> None:
        for filename in (
            "Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat",
            "sample_300K.dat",
            "sample_48HRS.dat",
            "sample_900C.dat",
            "Fe2CoGe.dat",
        ):
            with self.subTest(filename=filename):
                self.assertIsNone(self._filename_candidate(filename))

    def test_integer_and_uppercase_tokens_are_supported(self) -> None:
        for filename, expected, token in (
            ("sample_5mg.dat", 5.0, "5mg"),
            ("sample_12.75mg.dat", 12.75, "12.75mg"),
            ("sample_12P75MG.dat", 12.75, "12P75MG"),
            ("sample_5p4MG.dat", 5.4, "5p4MG"),
        ):
            with self.subTest(filename=filename):
                candidate = self._filename_candidate(filename)
                self.assertIsNotNone(candidate)
                self.assertAlmostEqual(candidate["value_mg"], expected, places=9)
                self.assertEqual(candidate["raw_value"], token)

    def test_magnesium_compounds_are_not_read_as_mass(self) -> None:
        # A false positive here would rescale every per-gram result by a
        # stoichiometric coefficient.
        for filename in ("Fe2MgO4_300K.dat", "Fe2Mg.dat", "MgO_900C.dat"):
            with self.subTest(filename=filename):
                self.assertIsNone(self._filename_candidate(filename))

    def test_directory_names_do_not_contribute_hints(self) -> None:
        for filename in (
            "/data/5mg_samples/Fe2CoGe_900C.dat",
            r"C:\data\5mg_samples\Fe2CoGe_900C.dat",
        ):
            with self.subTest(filename=filename):
                self.assertIsNone(self._filename_candidate(filename))

    def test_basename_of_a_path_is_still_searched(self) -> None:
        for filename in (
            "/data/batch7/Fe2CoGe_5p4mg.dat",
            r"C:\data\batch\Fe2CoGe_5p4mg.dat",
        ):
            with self.subTest(filename=filename):
                candidate = self._filename_candidate(filename)
                self.assertIsNotNone(candidate)
                self.assertAlmostEqual(candidate["value_mg"], 5.4, places=9)

    def test_filename_only_needs_confirmation(self) -> None:
        """TEST C resolution half: a filename alone cannot authorize anything."""
        result = resolve_sample_mass(_parsed(), filename="sample_5.4mg.dat")

        self.assertIsNone(result["resolved_mass_mg"])
        self.assertIsNone(result["resolved_source"])
        self.assertEqual(result["resolution_status"], "needs_confirmation")
        self.assertFalse(result["normalization_allowed"])
        self.assertTrue(
            any("not an instrument record" in w for w in result["warnings"]),
            f"Expected a confirmation-required warning, got: {result['warnings']}",
        )

    def test_non_string_filename_is_rejected(self) -> None:
        with self.assertRaises(SampleProvenanceError):
            resolve_sample_mass(_parsed(), filename=5.4)


class CrossPlatformBasenameTests(unittest.TestCase):
    """Basename extraction must not depend on the server operating system."""

    def _result(self, filename: str) -> dict[str, Any]:
        return resolve_sample_mass(_parsed(), filename=filename)

    def test_posix_directory_mass_is_not_a_hint(self) -> None:
        result = self._result("/data/5mg_samples/Fe2CoGe_900C.dat")

        self.assertEqual(result["filename_inspected"], "Fe2CoGe_900C.dat")
        self.assertEqual(_filename_candidates(result), [])
        self.assertEqual(result["filename_mass_hint_count"], 0)

    def test_windows_directory_mass_is_not_a_hint(self) -> None:
        result = self._result(r"C:\data\5mg_samples\Fe2CoGe_900C.dat")

        self.assertEqual(result["filename_inspected"], "Fe2CoGe_900C.dat")
        self.assertEqual(_filename_candidates(result), [])
        self.assertEqual(result["filename_mass_hint_count"], 0)

    def test_posix_basename_mass_is_found(self) -> None:
        result = self._result("/data/batch/Fe2CoGe_5p4mg.dat")

        self.assertEqual(result["filename_inspected"], "Fe2CoGe_5p4mg.dat")
        self.assertEqual(len(_filename_candidates(result)), 1)
        self.assertAlmostEqual(
            _filename_candidates(result)[0]["value_mg"], 5.4, places=9
        )
        self.assertEqual(_filename_candidates(result)[0]["raw_value"], "5p4mg")

    def test_windows_basename_mass_is_found(self) -> None:
        result = self._result(r"C:\data\batch\Fe2CoGe_5p4mg.dat")

        self.assertEqual(result["filename_inspected"], "Fe2CoGe_5p4mg.dat")
        self.assertEqual(len(_filename_candidates(result)), 1)
        self.assertAlmostEqual(
            _filename_candidates(result)[0]["value_mg"], 5.4, places=9
        )
        self.assertEqual(_filename_candidates(result)[0]["raw_value"], "5p4mg")


class ConflictTests(unittest.TestCase):
    """TEST E: header and filename disagree."""

    def setUp(self) -> None:
        self.result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}), filename=ORIGINAL_STYLE_FILENAME
        )

    def test_conflict_blocks_resolution(self) -> None:
        self.assertIsNone(self.result["resolved_mass_mg"])
        self.assertIsNone(self.result["resolved_source"])
        self.assertEqual(self.result["resolution_status"], "conflict")
        self.assertFalse(self.result["normalization_allowed"])
        self.assertFalse(self.result["sources_agree"])

    def test_both_candidates_survive_the_conflict(self) -> None:
        by_source = _candidates_by_source(self.result)
        self.assertEqual(set(by_source), {"instrument_header", "filename"})
        self.assertAlmostEqual(
            by_source["instrument_header"]["value_mg"], 3.5, places=9
        )
        self.assertAlmostEqual(by_source["filename"]["value_mg"], 5.4, places=9)

    def test_warning_names_both_values_and_sources(self) -> None:
        conflicts = [w for w in self.result["warnings"] if "disagree" in w]
        self.assertEqual(len(conflicts), 1)

        message = conflicts[0]
        self.assertIn("3.5 mg", message)
        self.assertIn("5.4 mg", message)
        self.assertIn("SAMPLE_MASS", message)
        self.assertIn("filename", message)
        self.assertIn("5p4mg", message)

    def test_warning_states_the_denominator_of_its_percentage(self) -> None:
        message = next(w for w in self.result["warnings"] if "disagree" in w)
        self.assertIn("1.9 mg", message)
        self.assertIn("larger value", message)


class ConsistentSourceTests(unittest.TestCase):
    """TESTS F and G: agreement, exact and within rounding tolerance."""

    def test_identical_sources_are_consistent(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}), filename="sample_3p5mg.dat"
        )

        self.assertEqual(result["resolution_status"], "consistent_sources")
        self.assertAlmostEqual(result["resolved_mass_mg"], 3.5, places=9)
        self.assertEqual(result["resolved_source"], "instrument_header")
        self.assertTrue(result["normalization_allowed"])
        self.assertTrue(result["sources_agree"])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(len(result["mass_candidates"]), 2)

    def test_rounding_difference_is_within_tolerance(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.50"}), filename="sample_3p52mg.dat"
        )

        self.assertEqual(result["resolution_status"], "consistent_sources")
        self.assertAlmostEqual(result["resolved_mass_mg"], 3.5, places=9)
        self.assertTrue(result["normalization_allowed"])
        self.assertEqual(result["warnings"], [])

    def test_resolved_value_comes_from_the_instrument_not_the_filename(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.50"}), filename="sample_3p52mg.dat"
        )
        # 3.50 rather than 3.52: the instrument record wins on agreement.
        self.assertAlmostEqual(result["resolved_mass_mg"], 3.50, places=9)
        self.assertEqual(result["resolved_source"], "instrument_header")

    def test_tolerances_are_configurable(self) -> None:
        strict = SampleProvenanceConfig(
            mass_relative_tolerance=0.0, mass_absolute_tolerance_mg=0.0
        )
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.50"}),
            filename="sample_3p52mg.dat",
            config=strict,
        )
        self.assertEqual(result["resolution_status"], "conflict")
        self.assertFalse(result["normalization_allowed"])

        loose = SampleProvenanceConfig(mass_relative_tolerance=0.5)
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}),
            filename="sample_5p4mg.dat",
            config=loose,
        )
        self.assertEqual(result["resolution_status"], "consistent_sources")

    def test_absolute_tolerance_helps_small_masses(self) -> None:
        # 0.1 vs 0.12 mg fails a 2% relative test but passes the 0.05 mg floor.
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "0.1"}), filename="sample_0p12mg.dat"
        )
        self.assertEqual(result["resolution_status"], "consistent_sources")

    def test_config_documented_as_non_physical(self) -> None:
        docstring = SampleProvenanceConfig.__doc__ or ""
        self.assertIn("rounding", docstring.lower())
        self.assertIn("not", docstring.lower())
        self.assertIn("physical uncertainty", docstring.lower())

    def test_config_defaults_and_validation(self) -> None:
        self.assertAlmostEqual(DEFAULT_CONFIG.mass_relative_tolerance, 0.02, places=9)
        self.assertAlmostEqual(
            DEFAULT_CONFIG.mass_absolute_tolerance_mg, 0.05, places=9
        )
        self.assertEqual(DEFAULT_CONFIG.instrument_mass_keys, ("SAMPLE_MASS",))

        for overrides in (
            {"mass_relative_tolerance": -0.01},
            {"mass_absolute_tolerance_mg": -0.01},
            {"instrument_mass_keys": ()},
        ):
            with self.subTest(**overrides):
                with self.assertRaises(SampleProvenanceError):
                    SampleProvenanceConfig(**overrides)


class InvalidHeaderMassTests(unittest.TestCase):
    """TEST H: zero, negative, and non-numeric header masses."""

    def _assert_rejected(self, raw: Any, expected_reason: str) -> dict[str, Any]:
        result = resolve_sample_mass(_parsed({"SAMPLE_MASS": raw}))

        self.assertEqual(
            result["mass_candidates"],
            [],
            "An invalid header mass must never become a usable candidate.",
        )
        self.assertIsNone(result["resolved_mass_mg"])
        self.assertEqual(result["resolution_status"], "missing")
        self.assertFalse(result["normalization_allowed"])

        self.assertEqual(len(result["rejected_candidates"]), 1)
        rejected = result["rejected_candidates"][0]
        # Identity, not equality: a preserved NaN is never equal to itself.
        self.assertIs(rejected["raw_value"], raw)
        self.assertEqual(rejected["source"], "instrument_header")
        self.assertIn(expected_reason, rejected["rejection_reason"])

        self.assertTrue(
            any("SAMPLE_MASS" in w for w in result["warnings"]),
            f"Expected a warning naming the key, got: {result['warnings']}",
        )
        return result

    def test_zero_mass_is_rejected(self) -> None:
        self._assert_rejected("0", "zero")
        self._assert_rejected("0.0", "zero")
        self._assert_rejected(0.0, "zero")

    def test_negative_mass_is_rejected(self) -> None:
        self._assert_rejected("-3.5", "negative")
        self._assert_rejected(-3.5, "negative")

    def test_non_numeric_mass_is_rejected(self) -> None:
        self._assert_rejected("unknown", "not numeric")
        self._assert_rejected("n/a", "not numeric")

    def test_non_finite_mass_is_rejected(self) -> None:
        self._assert_rejected(float("nan"), "not a finite number")
        self._assert_rejected(float("inf"), "not a finite number")

    def test_unexpected_unit_is_not_assumed_to_be_milligrams(self) -> None:
        result = self._assert_rejected("3.5 g", "not milligrams")
        self.assertTrue(
            any("refusing to guess" in w for w in result["warnings"]),
            f"Expected a unit-conversion refusal, got: {result['warnings']}",
        )

    def test_explicit_mg_unit_in_header_is_accepted(self) -> None:
        result = resolve_sample_mass(_parsed({"SAMPLE_MASS": "3.5 mg"}))
        self.assertAlmostEqual(result["resolved_mass_mg"], 3.5, places=9)
        self.assertEqual(result["mass_candidates"][0]["raw_value"], "3.5 mg")

    def test_invalid_header_leaves_filename_needing_confirmation(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "0"}), filename="sample_5p4mg.dat"
        )

        self.assertEqual(result["resolution_status"], "needs_confirmation")
        self.assertFalse(result["normalization_allowed"])
        self.assertEqual(len(result["mass_candidates"]), 1)
        self.assertEqual(len(result["rejected_candidates"]), 1)


AMBIGUOUS_FILENAME = "sample_3p5mg_reweighed_3p8mg.dat"


class FilenameAmbiguityTests(unittest.TestCase):
    """
    TEST I: several different mg tokens in one filename.

    Ambiguous is not the same state as missing: a mass was found, it just
    cannot be trusted without confirmation.
    """

    def setUp(self) -> None:
        self.result = resolve_sample_mass(_parsed(), filename=AMBIGUOUS_FILENAME)

    def test_ambiguity_needs_confirmation_rather_than_missing(self) -> None:
        self.assertEqual(self.result["resolution_status"], "needs_confirmation")
        self.assertNotEqual(self.result["resolution_status"], "missing")
        self.assertIsNone(self.result["resolved_mass_mg"])
        self.assertIsNone(self.result["resolved_source"])
        self.assertFalse(self.result["normalization_allowed"])

    def test_no_missing_mass_warning_is_emitted(self) -> None:
        self.assertEqual(
            [w for w in self.result["warnings"] if "No sample mass was found" in w],
            [],
            "Mass information was found; it is ambiguous, not absent.",
        )

    def test_both_values_remain_machine_readable(self) -> None:
        values = sorted(_candidate_values(self.result, "filename"))
        self.assertEqual(len(values), 2)
        self.assertAlmostEqual(values[0], 3.5, places=9)
        self.assertAlmostEqual(values[1], 3.8, places=9)

        self.assertEqual(self.result["filename_mass_hint_count"], 2)
        self.assertTrue(self.result["filename_masses_ambiguous"])
        self.assertFalse(self.result["sources_agree"])

    def test_each_hint_keeps_its_own_token(self) -> None:
        by_value = {
            round(candidate["value_mg"], 6): candidate
            for candidate in _filename_candidates(self.result)
        }
        self.assertEqual(by_value[3.5]["raw_value"], "3p5mg")
        self.assertEqual(by_value[3.5]["matched_tokens"], ["3p5mg"])
        self.assertEqual(by_value[3.8]["raw_value"], "3p8mg")
        self.assertEqual(by_value[3.8]["matched_tokens"], ["3p8mg"])

    def test_confirmation_required_warning_is_explicit(self) -> None:
        self.assertTrue(
            any(
                "ambiguous" in w and "confirmation is required" in w
                for w in self.result["warnings"]
            ),
            f"Expected an ambiguity-confirmation warning, got: {self.result['warnings']}",
        )

    def test_ambiguity_warning_lists_every_token(self) -> None:
        ambiguous = [w for w in self.result["warnings"] if "different" in w]
        self.assertEqual(len(ambiguous), 1)

        message = ambiguous[0]
        self.assertIn("3p5mg", message)
        self.assertIn("3p8mg", message)
        self.assertIn("3.5 mg", message)
        self.assertIn("3.8 mg", message)
        self.assertIn("guesswork", message)
        self.assertIn("kept as provenance", message)


class AmbiguousFilenameWithInstrumentTests(unittest.TestCase):
    """
    A valid instrument mass does not silently win over an explicitly
    conflicting filename mass.
    """

    def setUp(self) -> None:
        self.result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}), filename=AMBIGUOUS_FILENAME
        )

    def test_instrument_value_does_not_authorize_normalization(self) -> None:
        self.assertEqual(self.result["resolution_status"], "conflict")
        self.assertIsNone(self.result["resolved_mass_mg"])
        self.assertIsNone(self.result["resolved_source"])
        self.assertFalse(self.result["normalization_allowed"])

    def test_every_value_is_preserved(self) -> None:
        self.assertAlmostEqual(
            _candidate_values(self.result, "instrument_header")[0], 3.5, places=9
        )
        self.assertEqual(
            sorted(_candidate_values(self.result, "filename")), [3.5, 3.8]
        )

    def test_conflict_warning_explains_the_refusal(self) -> None:
        self.assertTrue(
            any(
                "not used on its own" in w and "3.8 mg" in w
                for w in self.result["warnings"]
            ),
            f"Expected an instrument-versus-ambiguity warning, got: {self.result['warnings']}",
        )

    def test_user_confirmation_resolves_but_keeps_provenance(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}),
            filename=AMBIGUOUS_FILENAME,
            user_confirmed_mass_mg=3.8,
        )

        self.assertEqual(result["resolution_status"], "user_confirmed")
        self.assertAlmostEqual(result["resolved_mass_mg"], 3.8, places=9)
        self.assertEqual(result["resolved_source"], "user_confirmed")
        self.assertTrue(result["normalization_allowed"])

        self.assertTrue(result["filename_masses_ambiguous"])
        self.assertFalse(result["sources_agree"])
        self.assertEqual(
            sorted(_candidate_values(result, "filename")), [3.5, 3.8]
        )
        self.assertTrue(
            any("different" in w for w in result["warnings"]),
            "The ambiguity provenance must survive confirmation.",
        )
        self.assertTrue(
            any(
                "confirmed mass" in w and "3.5 mg" in w for w in result["warnings"]
            ),
            f"Expected a disagreement note against 3.5 mg, got: {result['warnings']}",
        )


class RepeatedFilenameTokenTests(unittest.TestCase):
    """TEST D: equivalent tokens are one mass with both spellings kept."""

    def setUp(self) -> None:
        self.result = resolve_sample_mass(
            _parsed(), filename="sample_3p5mg_3.5mg.dat"
        )

    def test_one_numerical_mass(self) -> None:
        candidates = _filename_candidates(self.result)
        self.assertEqual(len(candidates), 1)
        self.assertAlmostEqual(candidates[0]["value_mg"], 3.5, places=9)
        self.assertEqual(self.result["filename_mass_hint_count"], 1)
        self.assertFalse(self.result["filename_masses_ambiguous"])

    def test_both_raw_tokens_preserved(self) -> None:
        candidate = _filename_candidates(self.result)[0]
        self.assertEqual(candidate["matched_tokens"], ["3p5mg", "3.5mg"])
        self.assertEqual(candidate["raw_value"], "3p5mg")

    def test_still_needs_confirmation_without_a_stronger_source(self) -> None:
        self.assertEqual(self.result["resolution_status"], "needs_confirmation")
        self.assertFalse(self.result["normalization_allowed"])
        self.assertTrue(
            any("repeats the same mass" in w for w in self.result["warnings"]),
            f"Expected a duplicate-token note, got: {self.result['warnings']}",
        )

    def test_duplicate_tokens_agree_with_instrument(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}), filename="sample_3p5mg_3.5mg.dat"
        )
        self.assertEqual(result["resolution_status"], "consistent_sources")
        self.assertTrue(result["normalization_allowed"])


class CandidateUnitTests(unittest.TestCase):
    """Every usable candidate states its unit; rejected ones do not inherit mg."""

    def test_every_valid_candidate_declares_mg(self) -> None:
        results = [
            resolve_sample_mass(
                _parsed({"SAMPLE_MASS": "3.5"}),
                filename=ORIGINAL_STYLE_FILENAME,
                user_confirmed_mass_mg=5.4,
            ),
            resolve_sample_mass(_parsed(), filename=AMBIGUOUS_FILENAME),
            resolve_sample_mass(_parsed({"SAMPLE_MASS": 3.5})),
            resolve_sample_mass(_parsed(), user_confirmed_mass_mg=4.2),
        ]
        seen_sources = set()
        for result in results:
            for candidate in result["mass_candidates"]:
                with self.subTest(source=candidate["source"]):
                    self.assertEqual(candidate["unit"], "mg")
                seen_sources.add(candidate["source"])

        self.assertEqual(
            seen_sources, {"instrument_header", "filename", "user_confirmed"}
        )

    def test_gram_value_is_not_relabelled_as_mg(self) -> None:
        result = resolve_sample_mass(_parsed({"SAMPLE_MASS": "3.5 g"}))

        self.assertEqual(result["mass_candidates"], [])
        rejected = result["rejected_candidates"][0]
        self.assertNotIn("unit", rejected)
        self.assertEqual(rejected["supplied_unit"], "g")
        self.assertEqual(rejected["raw_value"], "3.5 g")
        self.assertIn("not milligrams", rejected["rejection_reason"])
        self.assertEqual(result["resolution_status"], "missing")
        self.assertFalse(result["normalization_allowed"])


class UserConfirmationTests(unittest.TestCase):
    """TESTS J and K: explicit confirmation resolves without erasing history."""

    def setUp(self) -> None:
        self.result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}),
            filename=ORIGINAL_STYLE_FILENAME,
            user_confirmed_mass_mg=5.4,
        )

    def test_confirmation_resolves_the_mass(self) -> None:
        self.assertAlmostEqual(self.result["resolved_mass_mg"], 5.4, places=9)
        self.assertEqual(self.result["resolved_source"], "user_confirmed")
        self.assertEqual(self.result["resolution_status"], "user_confirmed")
        self.assertTrue(self.result["normalization_allowed"])

    def test_all_candidates_are_preserved(self) -> None:
        by_source = _candidates_by_source(self.result)
        self.assertEqual(
            set(by_source), {"instrument_header", "filename", "user_confirmed"}
        )
        self.assertAlmostEqual(
            by_source["instrument_header"]["value_mg"], 3.5, places=9
        )
        self.assertAlmostEqual(by_source["filename"]["value_mg"], 5.4, places=9)
        self.assertAlmostEqual(by_source["user_confirmed"]["value_mg"], 5.4, places=9)

    def test_historical_conflict_warning_is_retained(self) -> None:
        self.assertFalse(self.result["sources_agree"])
        conflicts = [w for w in self.result["warnings"] if "disagree" in w]
        self.assertTrue(conflicts, "The original conflict must not be erased.")
        self.assertIn("3.5 mg", conflicts[0])
        self.assertIn("5.4 mg", conflicts[0])

    def test_confirmation_conflicting_with_instrument_is_flagged(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}), user_confirmed_mass_mg=5.4
        )

        self.assertEqual(result["resolution_status"], "user_confirmed")
        self.assertTrue(result["normalization_allowed"])
        self.assertTrue(
            any(
                "confirmed mass" in w and "instrument header" in w
                for w in result["warnings"]
            ),
            f"Expected a confirmation-disagreement warning, got: {result['warnings']}",
        )

    def test_confirmation_agreeing_with_sources_is_quiet(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}),
            filename="sample_3p5mg.dat",
            user_confirmed_mass_mg=3.5,
        )

        self.assertEqual(result["resolution_status"], "user_confirmed")
        self.assertEqual(result["warnings"], [])

    def test_confirmation_alone_is_sufficient(self) -> None:
        result = resolve_sample_mass(_parsed(), user_confirmed_mass_mg=4.2)

        self.assertAlmostEqual(result["resolved_mass_mg"], 4.2, places=9)
        self.assertEqual(result["resolution_status"], "user_confirmed")
        self.assertTrue(result["normalization_allowed"])

    def test_invalid_confirmation_is_rejected(self) -> None:
        for value in (0, 0.0, -3.5, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(SampleProvenanceError):
                    resolve_sample_mass(
                        _parsed({"SAMPLE_MASS": "3.5"}),
                        user_confirmed_mass_mg=value,
                    )

    def test_non_numeric_confirmation_is_rejected(self) -> None:
        for value in ("3.5", True, [3.5]):
            with self.subTest(value=value):
                with self.assertRaises(SampleProvenanceError):
                    resolve_sample_mass(_parsed(), user_confirmed_mass_mg=value)

    def test_rejected_confirmation_does_not_fall_back_silently(self) -> None:
        # Raising rather than warning prevents a caller from believing a mass
        # was confirmed while the instrument value was quietly used instead.
        with self.assertRaises(SampleProvenanceError) as ctx:
            resolve_sample_mass(
                _parsed({"SAMPLE_MASS": "3.5"}), user_confirmed_mass_mg=0.0
            )
        self.assertIn("zero", str(ctx.exception))


class MissingInformationTests(unittest.TestCase):
    """CASE A: nothing to go on."""

    def test_no_metadata_and_no_filename(self) -> None:
        result = resolve_sample_mass(_parsed())

        self.assertEqual(result["mass_candidates"], [])
        self.assertIsNone(result["resolved_mass_mg"])
        self.assertIsNone(result["resolved_source"])
        self.assertEqual(result["resolution_status"], "missing")
        self.assertFalse(result["normalization_allowed"])
        self.assertIsNone(result["sources_agree"])
        self.assertTrue(
            any("No sample mass was found" in w for w in result["warnings"]),
            f"Expected a missing-mass warning, got: {result['warnings']}",
        )

    def test_absent_metadata_section_warns(self) -> None:
        result = resolve_sample_mass({"data": {}})

        self.assertEqual(result["resolution_status"], "missing")
        self.assertTrue(
            any("no metadata section" in w for w in result["warnings"]),
            f"Expected a metadata warning, got: {result['warnings']}",
        )

    def test_non_dict_parsed_input_raises(self) -> None:
        with self.assertRaises(SampleProvenanceError):
            resolve_sample_mass(["not", "a", "dict"])


class NoNormalizationTests(unittest.TestCase):
    def test_no_normalized_quantity_is_returned(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}), filename="sample_3p5mg.dat"
        )

        self.assertEqual(set(result) & FORBIDDEN_KEYS, set())
        for candidate in result["mass_candidates"]:
            self.assertEqual(set(candidate) & FORBIDDEN_KEYS, set())
        # Mass stays in mg; no gram-based or SI conversion is performed.
        self.assertEqual(result["units"], {"mass": "mg"})


class ModuleDocumentationTests(unittest.TestCase):
    def test_docstring_states_the_gap_without_a_bare_percentage(self) -> None:
        import services.sample_provenance as module

        docstring = module.__doc__ or ""
        self.assertIn("1.9 mg", docstring)
        self.assertNotIn("54%", docstring)

    def test_runtime_percentage_names_its_denominator(self) -> None:
        result = resolve_sample_mass(
            _parsed({"SAMPLE_MASS": "3.5"}), filename=ORIGINAL_STYLE_FILENAME
        )
        message = next(w for w in result["warnings"] if "disagree" in w)
        self.assertIn("%", message)
        self.assertIn("of the larger value", message)


class RealFe2CoGeProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parsed = parse_quantum_design_dat(
            FIXTURE_PATH.read_text(encoding="utf-8", errors="ignore")
        )
        cls.header_only = resolve_sample_mass(cls.parsed)
        cls.with_filename = resolve_sample_mass(
            cls.parsed, filename=ORIGINAL_STYLE_FILENAME
        )

    def test_header_reports_3p5_mg_from_the_instrument(self) -> None:
        self.assertEqual(self.parsed["metadata"]["SAMPLE_MASS"], "3.5")

        candidate = _candidates_by_source(self.header_only)["instrument_header"]
        self.assertAlmostEqual(candidate["value_mg"], 3.5, places=9)
        self.assertEqual(candidate["raw_value"], "3.5")
        self.assertEqual(candidate["source"], "instrument_header")
        self.assertEqual(candidate["source_key"], "SAMPLE_MASS")

    def test_header_alone_permits_normalization(self) -> None:
        self.assertAlmostEqual(self.header_only["resolved_mass_mg"], 3.5, places=9)
        self.assertEqual(self.header_only["resolution_status"], "instrument_metadata")
        self.assertTrue(self.header_only["normalization_allowed"])
        self.assertEqual(self.header_only["warnings"], [])

    def test_real_filename_contains_no_mass_token(self) -> None:
        # The fixture's own name has 48hrs and 900C but no mg token.
        result = resolve_sample_mass(self.parsed, filename=FIXTURE_PATH.name)
        self.assertIsNone(_candidates_by_source(result).get("filename"))
        self.assertEqual(result["resolution_status"], "instrument_metadata")

    def test_original_style_filename_creates_the_known_conflict(self) -> None:
        by_source = _candidates_by_source(self.with_filename)
        self.assertAlmostEqual(
            by_source["instrument_header"]["value_mg"], 3.5, places=9
        )
        self.assertAlmostEqual(by_source["filename"]["value_mg"], 5.4, places=9)

        self.assertIsNone(self.with_filename["resolved_mass_mg"])
        self.assertEqual(self.with_filename["resolution_status"], "conflict")
        self.assertFalse(self.with_filename["normalization_allowed"])

        message = next(w for w in self.with_filename["warnings"] if "disagree" in w)
        self.assertIn("3.5 mg", message)
        self.assertIn("5.4 mg", message)

    def test_parser_output_is_untouched_by_analysis(self) -> None:
        self.assertEqual(self.parsed["metadata"]["SAMPLE_MASS"], "3.5")
        self.assertEqual(self.parsed["metadata"]["SAMPLE_MATERIAL"], "Fe2CoGe")

    def test_report_provenance(self) -> None:
        lines = ["", "=== Fe2CoGe sample-mass provenance ===",
                 f"raw metadata SAMPLE_MASS = "
                 f"{self.parsed['metadata']['SAMPLE_MASS']!r}", ""]
        for label, result in (
            ("header only", self.header_only),
            (f"header + {ORIGINAL_STYLE_FILENAME}", self.with_filename),
        ):
            lines.append(f"--- {label} ---")
            for candidate in result["mass_candidates"]:
                lines.append(
                    f"    candidate: {candidate['value_mg']} mg  "
                    f"source={candidate['source']}  "
                    f"raw={candidate.get('raw_value')!r}"
                )
            if not result["mass_candidates"]:
                lines.append("    candidate: (none)")
            lines.append(f"    resolved_mass_mg      = {result['resolved_mass_mg']}")
            lines.append(f"    resolved_source       = {result['resolved_source']}")
            lines.append(f"    resolution_status     = {result['resolution_status']}")
            lines.append(
                f"    normalization_allowed = {result['normalization_allowed']}"
            )
            if result["warnings"]:
                for warning in result["warnings"]:
                    lines.append(f"    warning: {warning}")
            else:
                lines.append("    warning: (none)")
            lines.append("")
        print("\n".join(lines))
        self.assertEqual(self.with_filename["resolution_status"], "conflict")


if __name__ == "__main__":
    unittest.main()
