"""
Unified M-H analysis pipeline.

Composes the existing deterministic magnetometry modules into one auditable
result. This module orchestrates existing functions; it does not reimplement
their physics.

Parsing and segmentation are assumed to have already occurred. The caller
supplies one classified ``M-H`` segment.
"""

from __future__ import annotations

from typing import Any, Optional

from services.hysteresis import analyze_hysteresis
from services.mass_normalization import MassNormalizationError, normalize_moment_by_mass
from services.sample_provenance import resolve_sample_mass
from services.saturation import analyze_high_field_magnetization

SEGMENT_TYPE_MH = "M-H"


class MHAnalysisError(ValueError):
    """Raised when an M-H segment cannot be analyzed by this pipeline."""


def _aggregate_warnings(
    hysteresis: dict[str, Any],
    high_field: dict[str, Any],
    mass_provenance: dict[str, Any],
) -> list[str]:
    aggregated: list[str] = []
    for source, result in (
        ("hysteresis", hysteresis),
        ("high_field", high_field),
        ("mass_provenance", mass_provenance),
    ):
        for warning in result.get("warnings", []):
            aggregated.append(f"{source}: {warning}")
    return aggregated


def _normalize_moment(
    moment_emu: Optional[float], mass_provenance: dict[str, Any]
) -> Optional[dict[str, Any]]:
    if moment_emu is None:
        return None
    return normalize_moment_by_mass(moment_emu, mass_provenance)


def _build_normalized_results(
    hysteresis: dict[str, Any],
    high_field: dict[str, Any],
    mass_provenance: dict[str, Any],
) -> dict[str, Any]:
    """
    Build optional mass-normalized moment results.

    ``available`` means sample-mass normalization is authorized and can be
    applied. Individual normalized quantities may still be ``None`` when the
    corresponding raw quantity is unavailable.
    """
    reason = mass_provenance.get("resolution_status")
    unavailable = {
        "available": False,
        "reason": reason,
        "Mr_negative": None,
        "Mr_positive": None,
        "maximum_measured_moment": None,
        "moment_at_max_positive_field": None,
        "moment_at_max_negative_field": None,
    }

    if mass_provenance.get("normalization_allowed") is not True:
        return unavailable

    try:
        return {
            "available": True,
            "reason": reason,
            "Mr_negative": _normalize_moment(
                hysteresis.get("Mr_negative_emu"), mass_provenance
            ),
            "Mr_positive": _normalize_moment(
                hysteresis.get("Mr_positive_emu"), mass_provenance
            ),
            "maximum_measured_moment": _normalize_moment(
                high_field.get("maximum_absolute_measured_moment_emu"),
                mass_provenance,
            ),
            "moment_at_max_positive_field": _normalize_moment(
                high_field.get("moment_at_max_positive_field_emu"),
                mass_provenance,
            ),
            "moment_at_max_negative_field": _normalize_moment(
                high_field.get("moment_at_max_negative_field_emu"),
                mass_provenance,
            ),
        }
    except MassNormalizationError as exc:
        raise MHAnalysisError(
            "Mass provenance authorized normalization, but normalization failed: "
            f"{exc}"
        ) from exc


def analyze_mh_segment(
    parsed: dict[str, Any],
    segment: dict[str, Any],
    filename: Optional[str] = None,
    user_confirmed_mass_mg: Optional[float] = None,
) -> dict[str, Any]:
    """
    Run hysteresis, high-field, mass-provenance, and optional normalization
    analysis for one ``M-H`` segment.

    Parameters
    ----------
    parsed:
        Output of ``parse_quantum_design_dat``.
    segment:
        One segment from ``segment_measurements`` whose ``type`` is ``"M-H"``.
    filename:
        Optional original filename passed through to sample-mass provenance.
    user_confirmed_mass_mg:
        Optional user-confirmed sample mass in mg.

    Returns
    -------
    dict nesting the complete results from each underlying module plus an
    aggregated warning list and optional normalized moment results.

    The ``normalized["available"]`` flag means sample-mass normalization is
    authorized and can be applied. Individual entries under ``normalized`` may
    still be ``None`` when the corresponding raw quantity was unavailable.

    Raises
    ------
    MHAnalysisError
        If ``segment`` is not classified as ``"M-H"``, or if mass provenance
        authorized normalization but normalization failed unexpectedly.
    HysteresisAnalysisError, SaturationAnalysisError, SampleProvenanceError
        Propagated from the underlying modules when their inputs are invalid.
    """
    if not isinstance(parsed, dict):
        raise MHAnalysisError(
            f"Parsed input must be a dictionary, got {type(parsed).__name__}."
        )
    if not isinstance(segment, dict):
        raise MHAnalysisError(
            f"Segment must be a dictionary, got {type(segment).__name__}."
        )

    segment_type = segment.get("type")
    if segment_type != SEGMENT_TYPE_MH:
        raise MHAnalysisError(
            f"M-H analysis requires an '{SEGMENT_TYPE_MH}' segment, but the "
            f"supplied segment has type {segment_type!r}."
        )

    hysteresis = analyze_hysteresis(parsed, segment)
    high_field = analyze_high_field_magnetization(parsed, segment)
    mass_provenance = resolve_sample_mass(
        parsed,
        filename=filename,
        user_confirmed_mass_mg=user_confirmed_mass_mg,
    )
    normalized = _build_normalized_results(hysteresis, high_field, mass_provenance)

    return {
        "segment_type": SEGMENT_TYPE_MH,
        "segment": {
            "start_index": segment.get("start_index"),
            "end_index": segment.get("end_index"),
            "mean_temperature_K": segment.get("mean_temperature_K"),
        },
        "hysteresis": hysteresis,
        "high_field": high_field,
        "mass_provenance": mass_provenance,
        "normalized": normalized,
        "warnings": _aggregate_warnings(hysteresis, high_field, mass_provenance),
    }
