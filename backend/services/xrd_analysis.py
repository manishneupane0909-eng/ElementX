"""
Two-column XRD text analysis for scientific research experiments.

Parses measured 2θ (degrees) and intensity in acquisition order. Does not
assign hkl indices, identify phases, estimate lattice parameters, or apply
Scherrer / FWHM science.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import find_peaks

from services.parsers.quantum_design import is_quantum_design_dat

XRD_PIPELINE_VERSION = "1"
FORMAT_TWO_COLUMN_XRD_TEXT = "two_column_xrd_text"
MIN_XRD_POINTS = 5
ALLOWED_XRD_SUFFIXES = {".txt", ".csv", ".xy", ".dat"}
PEAK_PROMINENCE_FRACTION_OF_MAX = 0.02
PEAK_MIN_DISTANCE_POINTS = 10

_HEADER_KEYWORDS = (
    "theta",
    "angle",
    "field",
    "moment",
    "temp",
    "intensity",
    "header",
    "scan",
)


class InvalidXrdUploadError(ValueError):
    """Raised when an upload is not usable two-column XRD text."""


def analyze_xrd_bytes(content: bytes, filename: str) -> dict[str, Any]:
    """
    Decode, parse, and summarize a two-column XRD text file.

    Parameters
    ----------
    content:
        Original uploaded bytes (not mutated).
    filename:
        Original user filename, stored as metadata only.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_XRD_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_XRD_SUFFIXES))
        raise InvalidXrdUploadError(
            f"Unsupported XRD file type. Supported extensions: {allowed}."
        )

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidXrdUploadError("XRD file is not valid UTF-8 text.") from exc

    if is_quantum_design_dat(text):
        raise InvalidXrdUploadError(
            "This looks like a Quantum Design magnetometry .DAT file, not XRD data."
        )

    two_theta_deg, intensity, warnings = parse_xrd_text(text)
    if len(two_theta_deg) < MIN_XRD_POINTS:
        raise InvalidXrdUploadError(
            f"File contains too few valid 2θ/intensity points "
            f"(need at least {MIN_XRD_POINTS})."
        )
    if len(two_theta_deg) != len(intensity):
        raise InvalidXrdUploadError("2θ and intensity arrays are not aligned.")

    two_theta_min = min(two_theta_deg)
    two_theta_max = max(two_theta_deg)
    if two_theta_min == two_theta_max:
        raise InvalidXrdUploadError("Measured 2θ range is empty (all angles are identical).")

    intensity_min = min(intensity)
    intensity_max = max(intensity)

    peaks, peak_warnings = _candidate_intensity_maxima(two_theta_deg, intensity)
    warnings.extend(peak_warnings)

    return {
        "analysis_version": XRD_PIPELINE_VERSION,
        "file": {
            "filename": filename,
            "format": FORMAT_TWO_COLUMN_XRD_TEXT,
        },
        "series": {
            "two_theta_deg": two_theta_deg,
            "intensity": intensity,
        },
        "summary": {
            "point_count": len(two_theta_deg),
            "two_theta_min_deg": two_theta_min,
            "two_theta_max_deg": two_theta_max,
            "intensity_min": intensity_min,
            "intensity_max": intensity_max,
        },
        "peaks": peaks,
        "peak_detection": {
            "method": "scipy.signal.find_peaks",
            "label": "candidate_intensity_maxima",
            "prominence_fraction_of_max": PEAK_PROMINENCE_FRACTION_OF_MAX,
            "min_distance_points": PEAK_MIN_DISTANCE_POINTS,
        },
        "warnings": warnings,
    }


def parse_xrd_text(text: str) -> tuple[list[float], list[float], list[str]]:
    """
    Parse first two numeric columns as 2θ (degrees) and intensity.

    Acquisition order is preserved. Extra columns are not used as data;
    a warning is recorded instead of silently treating them as XRD values.
    """
    two_theta_deg: list[float] = []
    intensity: list[float] = []
    warnings: list[str] = []
    skipped_lines = 0
    extra_column_lines = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "*", "!", "%")):
            continue
        if any(keyword in line.lower() for keyword in _HEADER_KEYWORDS):
            continue

        values = [token.strip() for token in re.split(r"[\s+,;]+", line) if token.strip()]
        if len(values) < 2:
            skipped_lines += 1
            continue

        try:
            angle = float(values[0])
            signal = float(values[1])
        except ValueError:
            skipped_lines += 1
            continue

        if not math.isfinite(angle) or not math.isfinite(signal):
            skipped_lines += 1
            continue

        if len(values) > 2:
            extra_column_lines += 1

        two_theta_deg.append(angle)
        intensity.append(signal)

    if extra_column_lines:
        warnings.append(
            f"{extra_column_lines} data line(s) had more than two columns; "
            "only the first two numeric columns were used as 2θ and intensity."
        )
    if skipped_lines:
        warnings.append(
            f"{skipped_lines} line(s) were skipped because they were not two finite numbers."
        )

    return two_theta_deg, intensity, warnings


def suffix_for_xrd_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_XRD_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_XRD_SUFFIXES))
        raise InvalidXrdUploadError(
            f"Unsupported XRD file type. Supported extensions: {allowed}."
        )
    return suffix


def _candidate_intensity_maxima(
    two_theta_deg: list[float],
    intensity: list[float],
) -> tuple[list[dict[str, float]], list[str]]:
    warnings: list[str] = []
    intensity_array = np.asarray(intensity, dtype=float)
    if intensity_array.size == 0:
        return [], warnings

    maximum = float(np.nanmax(intensity_array))
    if not math.isfinite(maximum) or maximum <= 0:
        warnings.append("Candidate intensity maxima were not computed because intensity max is not positive.")
        return [], warnings

    peak_indices, _properties = find_peaks(
        intensity_array,
        prominence=PEAK_PROMINENCE_FRACTION_OF_MAX * maximum,
        distance=PEAK_MIN_DISTANCE_POINTS,
    )
    peaks = [
        {
            "two_theta_deg": float(two_theta_deg[int(index)]),
            "intensity": float(intensity[int(index)]),
        }
        for index in peak_indices
    ]
    return peaks, warnings
