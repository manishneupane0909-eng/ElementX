"""
Sample-mass provenance and conflict detection.

Any per-gram scientific result depends directly on the sample mass, so a wrong
mass silently rescales every derived quantity. This module therefore answers
only four questions:

  * what sample-mass information exists,
  * where each value came from,
  * whether the sources agree,
  * and whether normalization would be safe.

It performs no normalization. Nothing here computes emu/g, A*m^2/kg,
mu_B/f.u., Ms, or BHmax.

The motivating real case: a Quantum Design header reporting
``SAMPLE_MASS = 3.5`` alongside an original filename containing ``5p4mg``.
Those are 3.5 mg and 5.4 mg, a 1.9 mg disagreement that would materially
rescale every per-gram quantity. When sources disagree, this module refuses to
resolve a mass and blocks normalization until a human confirms the correct
value.

Every valid mass found is kept in ``mass_candidates`` as machine-readable
provenance, including several mutually inconsistent filename hints. Ambiguity
is therefore never hidden inside a warning string, and it is never reported as
missing information: a mass that was found but cannot be trusted is a different
state from no mass at all.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

MASS_UNIT = "mg"

SOURCE_INSTRUMENT = "instrument_header"
SOURCE_FILENAME = "filename"
SOURCE_USER = "user_confirmed"

STATUS_MISSING = "missing"
STATUS_INSTRUMENT = "instrument_metadata"
STATUS_CONSISTENT = "consistent_sources"
STATUS_NEEDS_CONFIRMATION = "needs_confirmation"
STATUS_CONFLICT = "conflict"
STATUS_USER_CONFIRMED = "user_confirmed"

INSTRUMENT_MASS_UNIT_ASSUMPTION = (
    "Quantum Design / MultiVu sample metadata records SAMPLE_MASS in "
    "milligrams; the raw header string is preserved alongside the interpreted "
    "value so the assumption stays auditable."
)

# An explicit "mg" unit is mandatory: there is deliberately no branch that
# matches a bare number, so tokens such as 900C, 48HRS, 300K, and the 2 in
# Fe2CoGe cannot be read as a mass. "p" between digits means a decimal point
# (5p4mg -> 5.4 mg).
#
# The two lookarounds suppress the realistic false positives:
#   * trailing  -> rejects magnesium compounds like Fe2MgO4, where "2Mg" is
#                  followed by another element letter;
#   * leading   -> rejects Fe2Mg.dat, where the 2 is stoichiometry, not mass.
# The leading guard also means a run-together name like sample5p4mg.dat is not
# matched. That is the intended trade-off: a false positive would rescale every
# per-gram result by a stoichiometric coefficient, whereas a false negative only
# asks the user to confirm the mass.
MASS_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(\d+(?:[.p]\d+)?)\s*mg(?![A-Za-z0-9])",
    re.IGNORECASE,
)


class SampleProvenanceError(ValueError):
    """Raised when sample-mass provenance cannot be evaluated at all."""


@dataclass(frozen=True)
class SampleProvenanceConfig:
    """
    Heuristic settings for sample-mass agreement.

    The tolerances exist to absorb ordinary rounding and metadata-entry
    differences -- a header typed as ``3.5`` against a filename written as
    ``3p52mg``, for instance. They are **not** physical uncertainty values, not
    a measurement error budget, and not a statement about balance precision.
    They are v1 bookkeeping thresholds and are expected to be tuned per lab
    workflow.

    Attributes
    ----------
    mass_relative_tolerance:
        Fractional agreement required between two mass sources.
    mass_absolute_tolerance_mg:
        Absolute agreement floor in mg, so that very small masses are not held
        to an unreachably tight relative comparison.
    instrument_mass_keys:
        Metadata keys inspected for an instrument-reported mass, in priority
        order. Values under these keys are interpreted as milligrams.
    """

    mass_relative_tolerance: float = 0.02
    mass_absolute_tolerance_mg: float = 0.05
    instrument_mass_keys: tuple[str, ...] = ("SAMPLE_MASS",)

    def __post_init__(self) -> None:
        if self.mass_relative_tolerance < 0:
            raise SampleProvenanceError(
                "mass_relative_tolerance must not be negative."
            )
        if self.mass_absolute_tolerance_mg < 0:
            raise SampleProvenanceError(
                "mass_absolute_tolerance_mg must not be negative."
            )
        if not self.instrument_mass_keys:
            raise SampleProvenanceError(
                "instrument_mass_keys must name at least one metadata key."
            )


DEFAULT_CONFIG = SampleProvenanceConfig()


def _format_mass(value: float) -> str:
    return f"{value:g}"


def _filename_basename(filename: str) -> str:
    """
    Return the final path component regardless of host operating system.

    ``pathlib.PurePath(...).name`` follows the local separator rules, so on a
    POSIX backend a Windows-style path such as ``C:\\data\\5mg_samples\\file.dat``
    is treated as a single component and directory names can leak into mass
    extraction. Normalizing both ``/`` and ``\\`` to ``/`` before taking the
    last segment avoids that.
    """
    normalized = filename.replace("\\", "/").rstrip("/")
    if not normalized:
        return filename
    return normalized.rsplit("/", 1)[-1] or filename


def _masses_agree(
    first: float, second: float, config: SampleProvenanceConfig
) -> bool:
    return math.isclose(
        first,
        second,
        rel_tol=config.mass_relative_tolerance,
        abs_tol=config.mass_absolute_tolerance_mg,
    )


def _relative_difference(first: float, second: float) -> Optional[float]:
    scale = max(abs(first), abs(second))
    if scale == 0.0:
        return None
    return abs(first - second) / scale


def _gap_phrase(first: float, second: float) -> str:
    """
    Describe a disagreement absolutely first, then relatively.

    A bare percentage is ambiguous because it depends on which value is the
    denominator, so the denominator is named explicitly.
    """
    phrase = f" (a gap of {_format_mass(abs(first - second))} mg"
    difference = _relative_difference(first, second)
    if difference is not None:
        phrase += f", {difference:.0%} of the larger value"
    return phrase + ")"


def _validate_positive_mass(value: float) -> Optional[str]:
    """Return a rejection reason, or None when the value is a usable mass."""
    if not math.isfinite(value):
        return "is not a finite number"
    if value == 0.0:
        return "is zero"
    if value < 0.0:
        return "is negative"
    return None


def _interpret_raw_mass(
    raw: Any,
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """
    Interpret a raw metadata mass value as milligrams.

    Returns ``(value_mg, rejection_reason, supplied_unit)``, where exactly one of
    the first two is set. ``supplied_unit`` records a unit that was written out
    in the raw value, so a value rejected for carrying grams is never relabelled
    as milligrams downstream. An unexpected unit is rejected rather than
    converted, because reading grams as milligrams would be a silent
    factor-of-1000 error.
    """
    if isinstance(raw, bool):
        return None, "is a boolean rather than a number", None

    if isinstance(raw, (int, float)):
        numeric = float(raw)
        reason = _validate_positive_mass(numeric)
        return (None, reason, None) if reason else (numeric, None, None)

    if not isinstance(raw, str):
        return None, f"has unsupported type {type(raw).__name__}", None

    text = raw.strip()
    if not text:
        return None, "is empty", None

    candidate = text
    supplied_unit: Optional[str] = None
    unit_match = re.fullmatch(
        r"(?P<number>[-+]?[0-9.eE+]+)\s*(?P<unit>[A-Za-z/]*)", text
    )
    if unit_match is not None:
        written = unit_match.group("unit")
        if written:
            supplied_unit = written
            if written.lower() != "mg":
                return (
                    None,
                    (
                        f"carries the unit {written!r}, which is not milligrams; "
                        "refusing to guess a conversion"
                    ),
                    supplied_unit,
                )
        candidate = unit_match.group("number")

    try:
        numeric = float(candidate)
    except ValueError:
        return None, "is not numeric", supplied_unit

    reason = _validate_positive_mass(numeric)
    return (
        (None, reason, supplied_unit) if reason else (numeric, None, supplied_unit)
    )


def _instrument_candidate(
    parsed: dict[str, Any],
    config: SampleProvenanceConfig,
    warnings: list[str],
    rejected: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    metadata = parsed.get("metadata")
    if metadata is None:
        warnings.append(
            "Parsed data carries no metadata section, so no instrument sample "
            "mass could be read."
        )
        return None
    if not isinstance(metadata, dict):
        warnings.append(
            "Parsed metadata is not a mapping, so no instrument sample mass "
            "could be read."
        )
        return None

    for key in config.instrument_mass_keys:
        if key not in metadata:
            continue

        raw = metadata[key]
        value_mg, reason, supplied_unit = _interpret_raw_mass(raw)
        if value_mg is None:
            if reason == "is empty":
                # Quantum Design writes empty INFO fields routinely; absence of
                # a value is not a malformed value.
                continue
            warnings.append(
                f"Instrument metadata {key} = {raw!r} {reason}, so it was not "
                "used as a sample mass. The invalid value was recorded but "
                "never substituted with a usable number."
            )
            # Deliberately carries no "unit" key: a value rejected for being in
            # grams must not be relabelled as milligrams.
            rejected.append(
                {
                    "source": SOURCE_INSTRUMENT,
                    "source_key": key,
                    "raw_value": raw,
                    "supplied_unit": supplied_unit,
                    "rejection_reason": reason,
                }
            )
            continue

        return {
            "value_mg": value_mg,
            "unit": MASS_UNIT,
            "raw_value": raw,
            "source": SOURCE_INSTRUMENT,
            "source_key": key,
        }

    return None


def _filename_hints(
    filename: Optional[str],
    config: SampleProvenanceConfig,
    warnings: list[str],
    rejected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Every distinct valid mass written explicitly in the filename.

    Tokens that repeat the same value collapse into one entry while keeping all
    their raw spellings. Mutually inconsistent values are all returned: they
    cannot be resolved automatically, but discarding them would turn found-but-
    ambiguous information into apparently missing information.
    """
    if filename is None:
        return []
    if not isinstance(filename, str):
        raise SampleProvenanceError(
            f"filename must be a string or None, got {type(filename).__name__}."
        )

    # Only the basename is searched, so a directory such as /data/5mg_samples/
    # cannot contribute a hint about this particular sample.
    basename = _filename_basename(filename)

    matches: list[dict[str, Any]] = []
    for match in MASS_TOKEN_PATTERN.finditer(basename):
        token = match.group(0).strip()
        number = match.group(1).replace("p", ".").replace("P", ".")
        try:
            value_mg = float(number)
        except ValueError:  # pragma: no cover - the pattern guarantees digits
            continue

        reason = _validate_positive_mass(value_mg)
        if reason:
            warnings.append(
                f"Filename token {token!r} {reason}, so it was not used as a "
                "sample mass."
            )
            rejected.append(
                {
                    "source": SOURCE_FILENAME,
                    "raw_value": token,
                    "supplied_unit": MASS_UNIT,
                    "rejection_reason": reason,
                }
            )
            continue

        matches.append((value_mg, token))

    if not matches:
        return []

    hints: list[dict[str, Any]] = []
    for value_mg, token in matches:
        for existing in hints:
            if _masses_agree(value_mg, existing["value_mg"], config):
                existing["matched_tokens"].append(token)
                break
        else:
            hints.append(
                {
                    "value_mg": value_mg,
                    "unit": MASS_UNIT,
                    "raw_value": token,
                    "source": SOURCE_FILENAME,
                    "matched_tokens": [token],
                }
            )

    if len(hints) > 1:
        listed = ", ".join(
            f"{hint['raw_value']} ({_format_mass(hint['value_mg'])} mg)"
            for hint in hints
        )
        warnings.append(
            f"The filename {basename!r} contains {len(hints)} different "
            f"explicit mass tokens: {listed}. All of them are kept as "
            "provenance, but no single filename mass was chosen because "
            "preferring one over the others would be guesswork."
        )
    elif len(matches) > 1:
        tokens = ", ".join(hints[0]["matched_tokens"])
        warnings.append(
            f"The filename {basename!r} repeats the same mass in "
            f"{len(matches)} tokens ({tokens}); they agree within tolerance and "
            "were treated as one value."
        )

    return hints


def _user_candidate(
    user_confirmed_mass_mg: Optional[float],
) -> Optional[dict[str, Any]]:
    if user_confirmed_mass_mg is None:
        return None

    if isinstance(user_confirmed_mass_mg, bool) or not isinstance(
        user_confirmed_mass_mg, (int, float)
    ):
        raise SampleProvenanceError(
            "user_confirmed_mass_mg must be a number, got "
            f"{type(user_confirmed_mass_mg).__name__}."
        )

    value_mg = float(user_confirmed_mass_mg)
    reason = _validate_positive_mass(value_mg)
    if reason:
        # A confirmation is a direct instruction rather than found data, so an
        # unusable one is refused outright. Downgrading it to a warning would
        # let the caller believe a mass was confirmed while a different value
        # was actually used.
        raise SampleProvenanceError(
            f"user_confirmed_mass_mg {user_confirmed_mass_mg!r} {reason}; a "
            "confirmed sample mass must be a finite positive number of "
            "milligrams."
        )

    return {"value_mg": value_mg, "unit": MASS_UNIT, "source": SOURCE_USER}


def _describe(candidate: dict[str, Any]) -> str:
    description = f"{_format_mass(candidate['value_mg'])} mg from "
    if candidate["source"] == SOURCE_INSTRUMENT:
        return description + f"the instrument header ({candidate['source_key']})"
    if candidate["source"] == SOURCE_FILENAME:
        return description + f"the filename (token {candidate['raw_value']!r})"
    return description + "user confirmation"


def resolve_sample_mass(
    parsed: dict[str, Any],
    filename: Optional[str] = None,
    user_confirmed_mass_mg: Optional[float] = None,
    config: Optional[SampleProvenanceConfig] = None,
) -> dict[str, Any]:
    """
    Collect sample-mass candidates, judge whether they agree, and decide whether
    normalization would be safe.

    Parameters
    ----------
    parsed:
        Output of ``parse_quantum_design_dat``. Never modified.
    filename:
        Optional original filename. Only explicit ``mg`` tokens are read from
        it; bare numbers are ignored.
    user_confirmed_mass_mg:
        Optional mass in mg explicitly confirmed by a human. Resolves the
        decision without erasing conflicting candidates or their warnings.
    config:
        Agreement tolerances. Defaults to :data:`DEFAULT_CONFIG`.

    Returns
    -------
    dict with every candidate and its provenance, the resolved mass (or None),
    a ``resolution_status``, and a ``normalization_allowed`` flag.

    Raises
    ------
    SampleProvenanceError
        If ``parsed`` is not a dict, ``filename`` is not a string, or
        ``user_confirmed_mass_mg`` is not a finite positive number.
    """
    settings = DEFAULT_CONFIG if config is None else config

    if not isinstance(parsed, dict):
        raise SampleProvenanceError(
            f"Parsed input must be a dictionary, got {type(parsed).__name__}."
        )

    warnings: list[str] = []
    rejected: list[dict[str, Any]] = []

    instrument = _instrument_candidate(parsed, settings, warnings, rejected)
    filename_hints = _filename_hints(filename, settings, warnings, rejected)
    user = _user_candidate(user_confirmed_mass_mg)

    # Every valid mass found stays in one list, so several inconsistent filename
    # hints remain machine-readable provenance instead of living only in a
    # warning string.
    candidates = [
        candidate
        for candidate in (instrument, *filename_hints, user)
        if candidate is not None
    ]

    filename_ambiguous = len(filename_hints) > 1
    single_filename = filename_hints[0] if len(filename_hints) == 1 else None

    # Agreement and conflict detection run independently of any user
    # confirmation, so a confirmation resolves the decision without erasing the
    # historical disagreement.
    discovered = [
        candidate for candidate in (instrument, *filename_hints) if candidate is not None
    ]
    sources_agree: Optional[bool] = None
    if len(discovered) > 1:
        sources_agree = all(
            _masses_agree(first["value_mg"], second["value_mg"], settings)
            for index, first in enumerate(discovered)
            for second in discovered[index + 1 :]
        )

    if instrument is not None and single_filename is not None and not sources_agree:
        warnings.append(
            "Sample mass sources disagree: the instrument header "
            f"{instrument['source_key']} reports "
            f"{_format_mass(instrument['value_mg'])} mg "
            f"(raw {instrument['raw_value']!r}) but the filename suggests "
            f"{_format_mass(single_filename['value_mg'])} mg (token "
            f"{single_filename['raw_value']!r})"
            f"{_gap_phrase(instrument['value_mg'], single_filename['value_mg'])}. "
            "No mass was resolved and normalization is blocked until the correct "
            "value is confirmed."
        )

    if user is not None:
        for other in discovered:
            if not _masses_agree(user["value_mg"], other["value_mg"], settings):
                warnings.append(
                    f"The confirmed mass of {_format_mass(user['value_mg'])} mg "
                    f"disagrees with {_describe(other)}. The confirmation was "
                    "used, but the disagreement is retained here as provenance."
                )
        resolution_status = STATUS_USER_CONFIRMED
        resolved_mass = user["value_mg"]
        resolved_source: Optional[str] = SOURCE_USER
        normalization_allowed = True

    elif filename_ambiguous:
        listed = ", ".join(
            f"{_format_mass(hint['value_mg'])} mg" for hint in filename_hints
        )
        if instrument is not None:
            # At most one of several mutually distinct hints can match the
            # instrument value, so an explicitly conflicting mass always exists
            # in the provenance and the instrument value cannot be trusted on
            # its own.
            warnings.append(
                "The instrument header "
                f"{instrument['source_key']} reports "
                f"{_format_mass(instrument['value_mg'])} mg, but the filename "
                f"records several explicit masses ({listed}) that cannot all "
                "agree with it. The instrument value was not used on its own; "
                "please confirm which mass is correct."
            )
            resolution_status = STATUS_CONFLICT
        else:
            warnings.append(
                f"The filename records several explicit masses ({listed}) and "
                "no instrument mass is available, so the sample mass was found "
                "but is ambiguous. Human confirmation is required before any "
                "normalization."
            )
            resolution_status = STATUS_NEEDS_CONFIRMATION
        resolved_mass = None
        resolved_source = None
        normalization_allowed = False

    elif instrument is not None and single_filename is not None:
        if sources_agree:
            resolution_status = STATUS_CONSISTENT
            resolved_mass = instrument["value_mg"]
            resolved_source = SOURCE_INSTRUMENT
            normalization_allowed = True
        else:
            resolution_status = STATUS_CONFLICT
            resolved_mass = None
            resolved_source = None
            normalization_allowed = False

    elif instrument is not None:
        resolution_status = STATUS_INSTRUMENT
        resolved_mass = instrument["value_mg"]
        resolved_source = SOURCE_INSTRUMENT
        normalization_allowed = True

    elif single_filename is not None:
        warnings.append(
            "The only sample mass found is the filename hint "
            f"{single_filename['raw_value']!r} "
            f"({_format_mass(single_filename['value_mg'])} mg). A filename is not "
            "an instrument record, so it cannot authorize automatic scientific "
            "normalization; please confirm the mass."
        )
        resolution_status = STATUS_NEEDS_CONFIRMATION
        resolved_mass = None
        resolved_source = None
        normalization_allowed = False

    else:
        warnings.append(
            "No sample mass was found in the instrument metadata or the "
            "filename, so no per-mass normalization is possible."
        )
        resolution_status = STATUS_MISSING
        resolved_mass = None
        resolved_source = None
        normalization_allowed = False

    return {
        "mass_candidates": candidates,
        "rejected_candidates": rejected,
        "resolved_mass_mg": resolved_mass,
        "resolved_source": resolved_source,
        "resolution_status": resolution_status,
        "normalization_allowed": normalization_allowed,
        "sources_agree": sources_agree,
        "filename_mass_hint_count": len(filename_hints),
        "filename_masses_ambiguous": filename_ambiguous,
        "filename_inspected": None if filename is None else _filename_basename(filename),
        "units": {"mass": MASS_UNIT},
        "instrument_mass_unit_assumption": INSTRUMENT_MASS_UNIT_ASSUMPTION,
        "warnings": warnings,
        "config": settings,
    }
