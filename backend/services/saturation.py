"""
High-field magnetization diagnostics for a single M-H measurement segment.

Answers one narrow question: what magnetization was actually measured at high
field, and does the loop provide evidence that magnetic saturation was
approached?

Nothing here proves or directly measures saturation. The reported
``saturation_evidence_quality`` is a heuristic reading of how flat the
high-field region is, which is why it is named for the strength of the evidence
rather than for saturation itself.

The maximum measured moment is reported as exactly that -- a measured maximum,
never as Ms. A linear model ``M(H) = intercept + slope * H`` is fitted
separately to the positive and negative high-field regions, but its zero-field
intercept is a *diagnostic extrapolation only*. Real approach-to-saturation
behavior can contain anisotropy-related 1/H and 1/H^2 terms, which a straight
line silently folds into its intercept, so that intercept is not automatically
the true saturation magnetization.

This module deliberately does not compute Ms, BHmax, Tc, anisotropy,
demagnetization corrections, or mass normalization. Values stay in raw
instrument units (Oe and emu).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

FIELD_ALIASES = ("Magnetic Field (Oe)",)
MOMENT_ALIASES = ("Moment (emu)",)

SEGMENT_TYPE_MH = "M-H"

QUALITY_HIGH = "high"
QUALITY_MEDIUM = "medium"
QUALITY_LOW = "low"
QUALITY_UNKNOWN = "unknown"

_QUALITY_BY_LEVEL = (QUALITY_HIGH, QUALITY_MEDIUM, QUALITY_LOW)
_WORST_LEVEL = len(_QUALITY_BY_LEVEL) - 1

_POSITIVE = "positive"
_NEGATIVE = "negative"


class SaturationAnalysisError(ValueError):
    """Raised when a segment cannot be analyzed for high-field behavior."""


@dataclass(frozen=True)
class SaturationConfig:
    """
    Heuristic settings for high-field magnetization diagnostics.

    Every threshold here is a **v1 diagnostic heuristic**, not a physical
    constant and not a universal saturation criterion. They were chosen from a
    sensitivity scan on a Quantum Design VSM +/-30 kOe loop and are expected to
    be revisited per material and per instrument.

    Attributes
    ----------
    high_field_fraction:
        A point counts as high-field when ``abs(H) >= fraction * max(abs(H))``.
        The 0.80 default keeps roughly the top fifth of the sweep: low enough to
        retain enough points for a stable fit, high enough to stay above the
        knee of the approach-to-saturation curve. Lowering it toward 0.7 pulls
        the knee into the window and inflates the fitted slope; raising it
        toward 0.9 leaves too few points and the slope becomes noise-dominated.
    minimum_high_field_points:
        Fewest high-field points on one polarity for a fit to be attempted.
    high_confidence_relative_slope:
        At or below this dimensionless slope the high-field region is treated as
        flat enough to call saturation evidence "high". The 0.02 default means
        the moment would change by under 2% of the measured moment scale across
        a field range equal to the maximum applied field.
    low_confidence_relative_slope:
        At or above this dimensionless slope the moment is still climbing
        strongly and saturation evidence is "low".
    maximum_relative_slope_disagreement:
        Fractional disagreement between the positive and negative relative
        slopes that is tolerated before confidence is reduced.
    maximum_high_field_asymmetry:
        Fractional magnitude asymmetry between the two field extremes that is
        tolerated before confidence is reduced.
    maximum_high_field_branch_separation:
        Tolerated separation between the increasing- and decreasing-field
        branches inside one high-field region, as a fraction of the moment
        scale. Branch agreement at high field is verified rather than assumed:
        if the branches disagree beyond this, they are still reported but a
        warning is raised and confidence is reduced instead of quietly
        averaging incompatible data.
    branch_direction_tolerance_Oe:
        Field step below which a point is treated as stabilization when tagging
        points by sweep direction for the branch-separation check.
    """

    high_field_fraction: float = 0.80
    minimum_high_field_points: int = 5
    high_confidence_relative_slope: float = 0.02
    low_confidence_relative_slope: float = 0.10
    maximum_relative_slope_disagreement: float = 0.5
    maximum_high_field_asymmetry: float = 0.05
    maximum_high_field_branch_separation: float = 0.01
    branch_direction_tolerance_Oe: float = 50.0

    def __post_init__(self) -> None:
        if not 0.0 < self.high_field_fraction < 1.0:
            raise SaturationAnalysisError(
                "high_field_fraction must lie strictly between 0 and 1."
            )
        if self.minimum_high_field_points < 2:
            raise SaturationAnalysisError(
                "minimum_high_field_points must be at least 2 to fit a line."
            )
        if self.high_confidence_relative_slope <= 0:
            raise SaturationAnalysisError(
                "high_confidence_relative_slope must be positive."
            )
        if self.low_confidence_relative_slope <= self.high_confidence_relative_slope:
            raise SaturationAnalysisError(
                "low_confidence_relative_slope must exceed "
                "high_confidence_relative_slope."
            )
        for name in (
            "maximum_relative_slope_disagreement",
            "maximum_high_field_asymmetry",
            "maximum_high_field_branch_separation",
        ):
            if getattr(self, name) <= 0:
                raise SaturationAnalysisError(f"{name} must be positive.")
        if self.branch_direction_tolerance_Oe < 0:
            raise SaturationAnalysisError(
                "branch_direction_tolerance_Oe must not be negative."
            )


DEFAULT_CONFIG = SaturationConfig()


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def _lookup_column(data: dict[str, Any], aliases: tuple[str, ...]) -> Optional[list[Any]]:
    normalized = {_normalize(key): key for key in data}
    for alias in aliases:
        key = normalized.get(_normalize(alias))
        if key is not None:
            return data[key]
    return None


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return float("nan")
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else float("nan")
    return float("nan")


def _required_column(
    data: dict[str, Any], aliases: tuple[str, ...], label: str
) -> list[float]:
    column = _lookup_column(data, aliases)
    if column is None:
        raise SaturationAnalysisError(
            f"Required column for {label} not found in parsed data. "
            f"Available columns: {sorted(data)}"
        )
    return [_as_float(value) for value in column]


def _ordinary_least_squares(
    xs: list[float], ys: list[float]
) -> Optional[tuple[float, float, Optional[float]]]:
    """
    Fit ``y = intercept + slope * x`` by ordinary least squares.

    Returns ``(slope, intercept, r_squared)``, where ``r_squared`` is None when
    the observations have no variance and the coefficient of determination is
    undefined. Returns None when the fit itself is impossible.
    """
    count = len(xs)
    if count < 2:
        return None

    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    if variance_x == 0.0:
        return None

    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = covariance / variance_x
    intercept = mean_y - slope * mean_x

    total = sum((y - mean_y) ** 2 for y in ys)
    if total == 0.0:
        return slope, intercept, None

    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    return slope, intercept, 1.0 - residual / total


def _sweep_directions(
    field: list[float], rows: list[int], tolerance: float
) -> dict[int, int]:
    """
    Tag each valid row with the sign of the field step that reached it.

    Steps within ``tolerance`` inherit the previous tag so stabilization points
    stay attached to the surrounding sweep. This only labels points for the
    branch-separation check; it does not segment the loop into branches.
    """
    tags: dict[int, int] = {}
    current = 0
    for position, row in enumerate(rows):
        if position > 0:
            step = field[row] - field[rows[position - 1]]
            if step > tolerance:
                current = 1
            elif step < -tolerance:
                current = -1
        tags[row] = current

    # The first point has no preceding step; adopt the first resolved direction.
    if rows and tags[rows[0]] == 0:
        for row in rows:
            if tags[row] != 0:
                tags[rows[0]] = tags[row]
                break

    return tags


def _branch_separation(
    field: list[float],
    moment: list[float],
    rows: list[int],
    directions: dict[int, int],
    slope: float,
    intercept: float,
    moment_scale: float,
) -> Optional[float]:
    """
    Measure how far the two sweep branches sit apart inside one high-field region.

    Residuals from the pooled fit are averaged per sweep direction, so the
    comparison is not confounded by the branches covering different field
    sub-ranges. Returned as a fraction of the moment scale, or None when one
    direction is not represented by at least two points.
    """
    grouped: dict[int, list[float]] = {1: [], -1: []}
    for row in rows:
        direction = directions.get(row, 0)
        if direction in grouped:
            grouped[direction].append(moment[row] - (intercept + slope * field[row]))

    if len(grouped[1]) < 2 or len(grouped[-1]) < 2 or moment_scale == 0.0:
        return None

    increasing = sum(grouped[1]) / len(grouped[1])
    decreasing = sum(grouped[-1]) / len(grouped[-1])
    return abs(increasing - decreasing) / moment_scale


def _fit_high_field_side(
    field: list[float],
    moment: list[float],
    rows: list[int],
    directions: dict[int, int],
    polarity: str,
    field_maximum: float,
    moment_scale: float,
    config: SaturationConfig,
    warnings: list[str],
) -> Optional[dict[str, Any]]:
    """Fit one field polarity's high-field region, or return None with a warning."""
    if len(rows) < config.minimum_high_field_points:
        warnings.append(
            f"Only {len(rows)} {polarity} high-field points are available "
            f"(minimum {config.minimum_high_field_points}); no {polarity} high-field "
            "fit was attempted."
        )
        return None

    fields = [field[row] for row in rows]
    moments = [moment[row] for row in rows]
    fit = _ordinary_least_squares(fields, moments)
    if fit is None:
        warnings.append(
            f"The {polarity} high-field region has no field variation; "
            "a slope could not be fitted."
        )
        return None

    slope, intercept, r_squared = fit
    if moment_scale > 0.0:
        relative_slope = abs(slope) * field_maximum / moment_scale
    else:
        relative_slope = None
        warnings.append(
            "The maximum absolute measured moment is zero, so the dimensionless "
            f"{polarity} high-field slope could not be computed."
        )

    separation = _branch_separation(
        field, moment, rows, directions, slope, intercept, moment_scale
    )

    return {
        "polarity": polarity,
        "point_count": len(rows),
        "slope_emu_per_Oe": slope,
        "extrapolated_intercept_emu": intercept,
        "r_squared": r_squared,
        "relative_slope": relative_slope,
        "field_range_Oe": [min(fields), max(fields)],
        "moment_range_emu": [min(moments), max(moments)],
        "branch_separation": separation,
        "source_index_first": rows[0],
        "source_index_last": rows[-1],
    }


def _quality_level(relative_slope: float, config: SaturationConfig) -> int:
    if relative_slope <= config.high_confidence_relative_slope:
        return 0
    if relative_slope >= config.low_confidence_relative_slope:
        return _WORST_LEVEL
    return 1


def analyze_high_field_magnetization(
    parsed: dict[str, Any],
    segment: dict[str, Any],
    config: Optional[SaturationConfig] = None,
) -> dict[str, Any]:
    """
    Assess the high-field behavior of one M-H segment.

    Parameters
    ----------
    parsed:
        Output of ``parse_quantum_design_dat``.
    segment:
        One segment from ``segment_measurements`` whose ``type`` is ``"M-H"``.
    config:
        Heuristic settings. Defaults to :data:`DEFAULT_CONFIG`.

    Returns
    -------
    dict describing the measured field extremes, the maximum measured moment,
    separate positive and negative high-field linear fits with dimensionless
    slope metrics, high-field symmetry, and a heuristic
    ``saturation_evidence_quality``. No quantity is presented as Ms.
    """
    settings = DEFAULT_CONFIG if config is None else config

    if not isinstance(parsed, dict):
        raise SaturationAnalysisError("Parsed input must be a dictionary.")
    if not isinstance(segment, dict):
        raise SaturationAnalysisError("Segment must be a dictionary.")

    segment_type = segment.get("type")
    if segment_type != SEGMENT_TYPE_MH:
        raise SaturationAnalysisError(
            f"High-field analysis requires an '{SEGMENT_TYPE_MH}' segment, but the "
            f"supplied segment has type {segment_type!r}."
        )

    data = parsed.get("data")
    if not isinstance(data, dict) or not data:
        raise SaturationAnalysisError("Parsed input has no 'data' columns.")

    field = _required_column(data, FIELD_ALIASES, "magnetic field")
    moment = _required_column(data, MOMENT_ALIASES, "moment")

    if len(field) != len(moment):
        raise SaturationAnalysisError(
            "Magnetic field and moment columns have different lengths "
            f"({len(field)} and {len(moment)} rows). Refusing to analyze misaligned "
            "columns."
        )

    row_count = len(field)
    if row_count == 0:
        raise SaturationAnalysisError("Parsed data contains no rows.")

    first_row = segment.get("start_index", 0)
    last_row = segment.get("end_index", row_count - 1)
    if not isinstance(first_row, int) or not isinstance(last_row, int):
        raise SaturationAnalysisError(
            "Segment start_index and end_index must be integers."
        )
    if first_row < 0:
        raise SaturationAnalysisError(f"Segment start_index {first_row} is negative.")
    if last_row < first_row:
        raise SaturationAnalysisError(
            f"Segment end_index {last_row} is before start_index {first_row}."
        )
    if last_row >= row_count:
        raise SaturationAnalysisError(
            f"Segment end_index {last_row} is outside the parsed data, which has "
            f"{row_count} rows (last valid index {row_count - 1})."
        )

    warnings: list[str] = []
    total_points = last_row - first_row + 1
    valid_rows = [
        row
        for row in range(first_row, last_row + 1)
        if math.isfinite(field[row]) and math.isfinite(moment[row])
    ]

    ignored = total_points - len(valid_rows)
    if ignored:
        warnings.append(
            f"{ignored} of {total_points} points in this segment have a non-finite "
            "field or moment and were ignored during analysis."
        )

    if len(valid_rows) < 2:
        raise SaturationAnalysisError(
            f"Only {len(valid_rows)} valid points in segment rows "
            f"{first_row}-{last_row}; at least 2 are required."
        )

    row_at_max_positive = max(valid_rows, key=lambda row: field[row])
    row_at_max_negative = min(valid_rows, key=lambda row: field[row])
    maximum_positive_field = field[row_at_max_positive]
    maximum_negative_field = field[row_at_max_negative]
    moment_at_max_positive = moment[row_at_max_positive]
    moment_at_max_negative = moment[row_at_max_negative]

    field_maximum = max(abs(field[row]) for row in valid_rows)
    moment_scale = max(abs(moment[row]) for row in valid_rows)

    high_field_threshold = settings.high_field_fraction * field_maximum
    positive_rows = [row for row in valid_rows if field[row] >= high_field_threshold]
    negative_rows = [row for row in valid_rows if field[row] <= -high_field_threshold]

    directions = _sweep_directions(
        field, valid_rows, settings.branch_direction_tolerance_Oe
    )

    positive_fit = _fit_high_field_side(
        field,
        moment,
        positive_rows,
        directions,
        _POSITIVE,
        field_maximum,
        moment_scale,
        settings,
        warnings,
    )
    negative_fit = _fit_high_field_side(
        field,
        moment,
        negative_rows,
        directions,
        _NEGATIVE,
        field_maximum,
        moment_scale,
        settings,
        warnings,
    )

    asymmetry = _magnitude_asymmetry(moment_at_max_positive, moment_at_max_negative)

    quality, disagreement = _classify_saturation(
        positive_fit, negative_fit, asymmetry, settings, warnings
    )

    return {
        "segment_type": SEGMENT_TYPE_MH,
        "start_index": first_row,
        "end_index": last_row,
        "point_count": total_points,
        "valid_point_count": len(valid_rows),
        "mean_temperature_K": segment.get("mean_temperature_K"),
        "maximum_positive_field_Oe": maximum_positive_field,
        "maximum_negative_field_Oe": maximum_negative_field,
        "moment_at_max_positive_field_emu": moment_at_max_positive,
        "moment_at_max_negative_field_emu": moment_at_max_negative,
        "maximum_absolute_measured_moment_emu": moment_scale,
        "source_index_at_max_positive_field": row_at_max_positive,
        "source_index_at_max_negative_field": row_at_max_negative,
        "high_field_threshold_Oe": high_field_threshold,
        "positive_high_field": positive_fit,
        "negative_high_field": negative_fit,
        "positive_high_field_slope_emu_per_Oe": _from_fit(
            positive_fit, "slope_emu_per_Oe"
        ),
        "negative_high_field_slope_emu_per_Oe": _from_fit(
            negative_fit, "slope_emu_per_Oe"
        ),
        "positive_high_field_extrapolated_intercept_emu": _from_fit(
            positive_fit, "extrapolated_intercept_emu"
        ),
        "negative_high_field_extrapolated_intercept_emu": _from_fit(
            negative_fit, "extrapolated_intercept_emu"
        ),
        "positive_high_field_r_squared": _from_fit(positive_fit, "r_squared"),
        "negative_high_field_r_squared": _from_fit(negative_fit, "r_squared"),
        "positive_relative_high_field_slope": _from_fit(positive_fit, "relative_slope"),
        "negative_relative_high_field_slope": _from_fit(negative_fit, "relative_slope"),
        "relative_slope_disagreement": disagreement,
        "high_field_magnitude_asymmetry": asymmetry,
        "saturation_evidence_quality": quality,
        "units": {
            "field": "Oe",
            "moment": "emu",
            "slope": "emu/Oe",
            "relative_slope": "dimensionless",
        },
        "relative_slope_definition": (
            "relative_slope = abs(slope) * max(abs(H)) / max(abs(M)); the fractional "
            "change in moment expected across a field range equal to the maximum "
            "applied field, relative to the maximum measured moment"
        ),
        "warnings": warnings,
        "config": settings,
    }


def _from_fit(fit: Optional[dict[str, Any]], key: str) -> Any:
    return None if fit is None else fit[key]


def _magnitude_asymmetry(
    moment_at_max_positive: float, moment_at_max_negative: float
) -> Optional[float]:
    """Fractional difference between the moment magnitudes at the two field extremes."""
    positive = abs(moment_at_max_positive)
    negative = abs(moment_at_max_negative)
    mean_magnitude = (positive + negative) / 2.0
    if mean_magnitude == 0.0:
        return None
    return abs(positive - negative) / mean_magnitude


def _classify_saturation(
    positive_fit: Optional[dict[str, Any]],
    negative_fit: Optional[dict[str, Any]],
    asymmetry: Optional[float],
    config: SaturationConfig,
    warnings: list[str],
) -> tuple[str, Optional[float]]:
    """Combine both polarities into a heuristic saturation-evidence label."""
    available = [fit for fit in (positive_fit, negative_fit) if fit is not None]
    scored = [fit for fit in available if fit["relative_slope"] is not None]

    disagreement: Optional[float] = None
    if len(scored) == 2:
        first, second = (fit["relative_slope"] for fit in scored)
        mean_slope = (first + second) / 2.0
        if mean_slope > 0.0:
            disagreement = abs(first - second) / mean_slope

    if not scored:
        warnings.append(
            "No high-field region provided enough data to judge saturation; "
            "saturation_evidence_quality is 'unknown'."
        )
        return QUALITY_UNKNOWN, disagreement

    level = max(_quality_level(fit["relative_slope"], config) for fit in scored)

    if len(scored) == 1:
        warnings.append(
            f"Saturation evidence rests on the {scored[0]['polarity']} high-field "
            "region only; the opposite polarity could not be fitted, so the two "
            "polarities could not corroborate each other and evidence quality was "
            "reduced by one level."
        )
        level = min(_WORST_LEVEL, level + 1)

    if disagreement is not None and disagreement > config.maximum_relative_slope_disagreement:
        warnings.append(
            f"The positive and negative high-field slopes disagree by "
            f"{disagreement:.1%}, above the tolerated "
            f"{config.maximum_relative_slope_disagreement:.1%}; saturation "
            "confidence was reduced."
        )
        level = min(_WORST_LEVEL, level + 1)

    if asymmetry is not None and asymmetry > config.maximum_high_field_asymmetry:
        warnings.append(
            f"The moment magnitudes at the two field extremes differ by "
            f"{asymmetry:.1%}, above the tolerated "
            f"{config.maximum_high_field_asymmetry:.1%}; the loop may be offset or "
            "the background subtraction may be incomplete. The data was not "
            "corrected and saturation confidence was reduced."
        )
        level = min(_WORST_LEVEL, level + 1)

    for fit in available:
        separation = fit["branch_separation"]
        if separation is not None and separation > config.maximum_high_field_branch_separation:
            warnings.append(
                f"The increasing- and decreasing-field branches of the "
                f"{fit['polarity']} high-field region are separated by "
                f"{separation:.2%} of the moment scale, above the tolerated "
                f"{config.maximum_high_field_branch_separation:.2%}. The branches "
                "were pooled for the fit but the result mixes data that does not "
                "agree; saturation confidence was reduced."
            )
            level = min(_WORST_LEVEL, level + 1)

    return _QUALITY_BY_LEVEL[level], disagreement
