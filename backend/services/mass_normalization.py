"""
Mass normalization for magnetic moments.

Converts a raw magnetic moment in emu to specific magnetization (magnetic
moment per unit mass) only when
:func:`services.sample_provenance.resolve_sample_mass` has explicitly
authorized normalization.

The returned A*m^2/kg value is specific magnetization, not ordinary SI
magnetization M, which has units A/m.

This function normalizes a supplied moment. It does not decide what that moment
physically represents. A mass-normalized maximum measured moment is still a
mass-normalized measured moment — not Ms, not saturation magnetization, and not
BHmax.
"""

from __future__ import annotations

import math
from typing import Any, Optional

MASS_UNIT = "mg"
MOMENT_UNIT = "emu"
CGS_SPECIFIC_MAGNETIZATION_UNIT = "emu/g"
SI_SPECIFIC_MAGNETIZATION_UNIT = "A*m^2/kg"

# Exact equivalence: 1 emu = 1e-3 A*m^2 and 1 g = 1e-3 kg, so
# (emu / g) and (A*m^2 / kg) share the same numerical value for specific
# magnetization. This is magnetic moment per unit mass, not ordinary
# magnetization M in A/m.
SI_EQUIVALENCE_NOTE = (
    "1 emu/g equals 1 A*m^2/kg exactly because 1 emu = 1e-3 A*m^2 and "
    "1 g = 1e-3 kg; no additional numerical factor is applied. Both units "
    "describe specific magnetization (magnetic moment per unit mass), not "
    "ordinary magnetization M in A/m."
)

AUTHORIZED_RESOLUTION_STATUSES = frozenset(
    {
        "instrument_metadata",
        "consistent_sources",
        "user_confirmed",
    }
)


class MassNormalizationError(ValueError):
    """Raised when a moment cannot be normalized by the supplied provenance."""


def _status_label(resolution_status: Any) -> str:
    if resolution_status is None:
        return "unknown"
    if isinstance(resolution_status, str):
        return resolution_status
    return repr(resolution_status)


def _as_finite_moment(moment_emu: Any) -> float:
    if isinstance(moment_emu, bool) or not isinstance(moment_emu, (int, float)):
        raise MassNormalizationError(
            f"moment_emu must be a number, got {type(moment_emu).__name__}."
        )

    numeric = float(moment_emu)
    if not math.isfinite(numeric):
        raise MassNormalizationError(
            f"moment_emu must be finite, got {moment_emu!r}."
        )
    return numeric


def _validated_mass_provenance(mass_provenance: dict[str, Any]) -> tuple[float, str, str]:
    if not isinstance(mass_provenance, dict):
        raise MassNormalizationError(
            f"mass_provenance must be a dictionary, got {type(mass_provenance).__name__}."
        )

    resolution_status = mass_provenance.get("resolution_status")
    status = _status_label(resolution_status)

    if mass_provenance.get("normalization_allowed") is not True:
        raise MassNormalizationError(
            "Mass normalization is blocked by sample-mass provenance "
            f"(resolution_status={status!r})."
        )

    if (
        not isinstance(resolution_status, str)
        or resolution_status not in AUTHORIZED_RESOLUTION_STATUSES
    ):
        raise MassNormalizationError(
            "Mass normalization requires an authorized sample-mass "
            f"resolution_status, got {status!r}."
        )

    resolved_source = mass_provenance.get("resolved_source")
    if not isinstance(resolved_source, str) or not resolved_source.strip():
        raise MassNormalizationError(
            "Mass normalization requires a non-empty resolved_source string, "
            f"got {resolved_source!r} (resolution_status={status!r})."
        )

    resolved_mass_mg = mass_provenance.get("resolved_mass_mg")
    if resolved_mass_mg is None:
        raise MassNormalizationError(
            "Mass normalization requires a resolved mass, but resolved_mass_mg "
            f"is missing (resolution_status={status!r})."
        )

    if isinstance(resolved_mass_mg, bool) or not isinstance(
        resolved_mass_mg, (int, float)
    ):
        raise MassNormalizationError(
            "Mass normalization requires a numeric resolved_mass_mg, got "
            f"{type(resolved_mass_mg).__name__} (resolution_status={status!r})."
        )

    mass_mg = float(resolved_mass_mg)
    if not math.isfinite(mass_mg):
        raise MassNormalizationError(
            f"resolved_mass_mg must be finite, got {resolved_mass_mg!r} "
            f"(resolution_status={status!r})."
        )
    if mass_mg <= 0.0:
        raise MassNormalizationError(
            f"resolved_mass_mg must be positive, got {resolved_mass_mg!r} "
            f"(resolution_status={status!r})."
        )

    return mass_mg, resolved_source, resolution_status


def normalize_moment_by_mass(
    moment_emu: float,
    mass_provenance: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize one magnetic moment by an authorized sample mass.

    Parameters
    ----------
    moment_emu:
        Raw magnetic moment in emu. Sign is preserved.
    mass_provenance:
        Output of :func:`services.sample_provenance.resolve_sample_mass`.

    Returns
    -------
    dict with CGS and SI specific-magnetization values and the mass provenance
    fields used for the calculation.

    Raises
    ------
    MassNormalizationError
        If normalization is not authorized, the provenance is malformed, or the
        moment is not a finite number.
    """
    moment = _as_finite_moment(moment_emu)
    resolved_mass_mg, mass_source, resolution_status = _validated_mass_provenance(
        mass_provenance
    )

    resolved_mass_g = resolved_mass_mg / 1000.0
    specific_magnetization_emu_per_g = moment / resolved_mass_g

    return {
        "input_moment_emu": moment,
        "resolved_mass_mg": resolved_mass_mg,
        "resolved_mass_g": resolved_mass_g,
        "mass_source": mass_source,
        "mass_resolution_status": resolution_status,
        "specific_magnetization_emu_per_g": specific_magnetization_emu_per_g,
        "specific_magnetization_Am2_per_kg": specific_magnetization_emu_per_g,
        "si_equivalence_note": SI_EQUIVALENCE_NOTE,
        "units": {
            "input_moment": MOMENT_UNIT,
            "mass": MASS_UNIT,
            "specific_magnetization_cgs": CGS_SPECIFIC_MAGNETIZATION_UNIT,
            "specific_magnetization_si": SI_SPECIFIC_MAGNETIZATION_UNIT,
        },
    }
