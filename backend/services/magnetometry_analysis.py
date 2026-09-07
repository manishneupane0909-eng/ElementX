"""
Whole-file Quantum Design magnetometry analysis.

Turns one Quantum Design / VersaLab .DAT file into one coherent experiment-level
result by composing the existing parser, segmentation, and unified M-H analysis
modules. This service orchestrates those functions; it does not reimplement their
physics.

M-T segments are identification-only. This module does not calculate Tc or
apply M-H physics to non-loop segments.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from services.magnetometry import segment_measurements
from services.mh_analysis import analyze_mh_segment
from services.parsers.quantum_design import parse_quantum_design_dat

FORMAT_QUANTUM_DESIGN_DAT = "quantum_design_dat"
SEGMENT_TYPE_MH = "M-H"


def _aggregate_warnings(
    parsed: dict[str, Any],
    segmentation: dict[str, Any],
    mh_analyses: list[dict[str, Any]],
) -> list[str]:
    aggregated: list[str] = []
    for warning in parsed.get("warnings", []):
        aggregated.append(f"parser: {warning}")
    for warning in segmentation.get("warnings", []):
        aggregated.append(f"segmentation: {warning}")
    for entry in mh_analyses:
        index = entry["segment_index"]
        for warning in entry["analysis"].get("warnings", []):
            aggregated.append(f"M-H segment {index}: {warning}")
    return aggregated


def _build_summary(
    segments: list[dict[str, Any]],
    mh_analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = Counter(segment.get("type") for segment in segments)
    return {
        "mh_segment_count": counts.get(SEGMENT_TYPE_MH, 0),
        "mt_segment_count": counts.get("M-T", 0),
        "unknown_segment_count": counts.get("unknown", 0),
        "normalization_available": (
            all(entry["analysis"]["normalized"]["available"] for entry in mh_analyses)
            if mh_analyses
            else False
        ),
    }


def analyze_quantum_design_magnetometry(
    text: str,
    filename: Optional[str] = None,
    user_confirmed_mass_mg: Optional[float] = None,
) -> dict[str, Any]:
    """
    Parse, segment, and analyze every M-H loop in one Quantum Design .DAT file.

    Parameters
    ----------
    text:
        Full file contents.
    filename:
        Optional original filename passed through to sample-mass provenance for
        every M-H segment from the same physical sample.
    user_confirmed_mass_mg:
        Optional user-confirmed sample mass in mg, applied consistently to all
        M-H segments.

    Returns
    -------
    dict with file metadata, the complete segmentation result, unified M-H
    analyses keyed by segment index, and an experiment summary.

    Raises
    ------
    QuantumDesignParseError
        If the file cannot be parsed.
    MagnetometrySegmentationError, MHAnalysisError
        Propagated from underlying modules when inputs are invalid.
    """
    parsed = parse_quantum_design_dat(text)
    segmentation = segment_measurements(parsed)
    segments = segmentation["segments"]

    mh_analyses: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        if segment.get("type") != SEGMENT_TYPE_MH:
            continue
        mh_analyses.append(
            {
                "segment_index": index,
                "analysis": analyze_mh_segment(
                    parsed,
                    segment,
                    filename=filename,
                    user_confirmed_mass_mg=user_confirmed_mass_mg,
                ),
            }
        )

    return {
        "file": {
            "filename": filename,
            "format": FORMAT_QUANTUM_DESIGN_DAT,
        },
        "metadata": parsed.get("metadata", {}),
        "segmentation": {
            "segment_count": len(segments),
            "warnings": segmentation.get("warnings", []),
            "segments": segments,
            "config": segmentation.get("config"),
        },
        "mh_analyses": mh_analyses,
        "summary": _build_summary(segments, mh_analyses),
        "warnings": _aggregate_warnings(parsed, segmentation, mh_analyses),
    }
