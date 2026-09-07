"""
Branch-aware hysteresis analysis for a single M-H measurement segment.

Extracts branch-specific coercive field and remanent moment from the original
measurement order. The sweep order carries the physics: moment is a two-valued
function of field, so the data is never sorted by field.

Scope is deliberately limited to Hc and Mr extraction. This module does not fit
saturation, compute Ms or BHmax, apply demagnetization corrections, or normalize
by sample mass. All values stay in raw instrument units (Oe and emu).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional

FIELD_ALIASES = ("Magnetic Field (Oe)",)
MOMENT_ALIASES = ("Moment (emu)",)
TEMPERATURE_ALIASES = ("Temperature (K)",)

SEGMENT_TYPE_MH = "M-H"

DIRECTION_INCREASING = "increasing"
DIRECTION_DECREASING = "decreasing"

_NEGATIVE = "negative"
_POSITIVE = "positive"


class HysteresisAnalysisError(ValueError):
    """Raised when a segment cannot be analyzed as a hysteresis loop."""


@dataclass(frozen=True)
class HysteresisConfig:
    """
    Heuristic tolerances for hysteresis branch analysis.

    These are v1 heuristic defaults tuned to Quantum Design VSM behavior, not
    physical constants. A later version may estimate them from the observed
    field-step distribution of the segment instead of using fixed values.

    Attributes
    ----------
    field_direction_tolerance_Oe:
        Consecutive field steps smaller than this are treated as field
        stabilization rather than sweep motion. Such steps stay attached to the
        surrounding branch instead of starting a new one.
    minimum_branch_points:
        A run of consistent sweep direction shorter than this is reported as an
        unclassified region rather than being forced into a hysteresis branch.
    minimum_valid_points:
        Fewest valid points in the segment for analysis to be attempted at all.
    """

    field_direction_tolerance_Oe: float = 50.0
    minimum_branch_points: int = 4
    minimum_valid_points: int = 4

    def __post_init__(self) -> None:
        if self.field_direction_tolerance_Oe < 0:
            raise HysteresisAnalysisError(
                "field_direction_tolerance_Oe must not be negative."
            )
        for name, minimum in (("minimum_branch_points", 2), ("minimum_valid_points", 2)):
            if getattr(self, name) < minimum:
                raise HysteresisAnalysisError(f"{name} must be at least {minimum}.")


DEFAULT_CONFIG = HysteresisConfig()


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
        raise HysteresisAnalysisError(
            f"Required column for {label} not found in parsed data. "
            f"Available columns: {sorted(data)}"
        )
    return [_as_float(value) for value in column]


def _direction_name(sign: int) -> str:
    return DIRECTION_INCREASING if sign > 0 else DIRECTION_DECREASING


def _sweep_runs(
    field: list[float],
    positions: list[int],
    config: HysteresisConfig,
) -> list[tuple[int, int, int]]:
    """
    Group valid positions into runs of consistent sweep direction.

    Returns ``(direction_sign, first, last)`` triples in valid-position space.
    Steps within the direction tolerance do not break a run, so field
    stabilization stays attached to the surrounding branch. Runs are disjoint;
    a turning point closes the branch that reached it.
    """
    if len(positions) < 2:
        return []

    tolerance = config.field_direction_tolerance_Oe
    runs: list[tuple[int, int, int]] = []
    direction = 0
    start = 0

    for index in range(1, len(positions)):
        step = field[positions[index]] - field[positions[index - 1]]
        if step > tolerance:
            sign = 1
        elif step < -tolerance:
            sign = -1
        else:
            continue

        if direction == 0:
            direction = sign
        elif sign != direction:
            runs.append((direction, start, index - 1))
            direction = sign
            start = index

    runs.append((direction, start, len(positions) - 1))
    return [run for run in runs if run[0] != 0]


def _interpolate_zero(x1: float, y1: float, x2: float, y2: float) -> Optional[float]:
    """Interpolate x where y crosses zero, using only these two neighbouring points."""
    if y2 == y1:
        return None
    return x1 + (0.0 - y1) * (x2 - x1) / (y2 - y1)


def _zero_crossing_pairs(
    values: list[float], positions: list[int], start: int, end: int
) -> list[tuple[int, int]]:
    """
    Find adjacent position pairs bracketing a sign change in ``values``.

    A point that is exactly zero is consumed by the first bracket containing it,
    so it is never reported by two brackets.
    """
    pairs: list[tuple[int, int]] = []
    index = start + 1
    while index <= end:
        first = values[positions[index - 1]]
        second = values[positions[index]]

        if first == 0.0 and second == 0.0:
            index += 1
            continue

        if first * second <= 0.0:
            pairs.append((index - 1, index))
            if second == 0.0:
                index += 2
                continue
        index += 1

    return pairs


def _record_by_sign(
    slots: dict[str, Optional[dict[str, Any]]],
    value: float,
    bracket: dict[str, Any],
    resolution: float,
    label: str,
    warnings: list[str],
) -> None:
    """File an interpolated value into the negative or positive slot by its own sign."""
    key = _NEGATIVE if value < 0 else _POSITIVE
    if value == 0.0:
        warnings.append(
            f"The {label} on the {bracket['branch_direction']} branch interpolated to "
            f"exactly zero; it is recorded as the {_POSITIVE} value."
        )

    if slots[key] is not None:
        warnings.append(
            f"A {key} {label} was already recorded; ignoring the crossing at rows "
            f"{bracket['source_index_1']}-{bracket['source_index_2']} on the "
            f"{bracket['branch_direction']} branch."
        )
        return

    slots[key] = {"value": value, "bracket": bracket, "resolution": resolution}


def _extract_branch_crossings(
    crossing_of: list[float],
    interpolated_over: list[float],
    field: list[float],
    moment: list[float],
    positions: list[int],
    start: int,
    end: int,
    direction: str,
    slots: dict[str, Optional[dict[str, Any]]],
    label: str,
    warnings: list[str],
) -> None:
    """Interpolate each zero-crossing of ``crossing_of`` on one branch."""
    pairs = _zero_crossing_pairs(crossing_of, positions, start, end)
    if len(pairs) > 1:
        warnings.append(
            f"{len(pairs)} {label} zero-crossings were found on the {direction} "
            "branch; they are filed by sign and same-sign duplicates are ignored."
        )

    for left, right in pairs:
        row_1 = positions[left]
        row_2 = positions[right]
        value = _interpolate_zero(
            interpolated_over[row_1],
            crossing_of[row_1],
            interpolated_over[row_2],
            crossing_of[row_2],
        )
        if value is None:
            warnings.append(
                f"Could not interpolate the {label} between rows {row_1} and {row_2}: "
                "the bracketing points have identical values."
            )
            continue

        bracket = {
            "H1_Oe": field[row_1],
            "M1_emu": moment[row_1],
            "H2_Oe": field[row_2],
            "M2_emu": moment[row_2],
            "source_index_1": row_1,
            "source_index_2": row_2,
            "branch_direction": direction,
        }
        _record_by_sign(
            slots,
            value,
            bracket,
            abs(field[row_2] - field[row_1]),
            label,
            warnings,
        )


def _slot_value(slots: dict[str, Optional[dict[str, Any]]], key: str) -> Optional[float]:
    record = slots[key]
    return None if record is None else record["value"]


def _slot_bracket(
    slots: dict[str, Optional[dict[str, Any]]], key: str
) -> Optional[dict[str, Any]]:
    record = slots[key]
    return None if record is None else record["bracket"]


def _slot_resolution(
    slots: dict[str, Optional[dict[str, Any]]], key: str
) -> Optional[float]:
    record = slots[key]
    return None if record is None else record["resolution"]


def analyze_hysteresis(
    parsed: dict[str, Any],
    segment: dict[str, Any],
    config: Optional[HysteresisConfig] = None,
) -> dict[str, Any]:
    """
    Analyze one M-H segment for branch-specific coercivity and remanence.

    Parameters
    ----------
    parsed:
        Output of ``parse_quantum_design_dat``.
    segment:
        One segment from ``segment_measurements`` whose ``type`` is ``"M-H"``.
    config:
        Heuristic tolerances. Defaults to :data:`DEFAULT_CONFIG`.

    Returns
    -------
    dict holding branch ranges, branch-specific Hc and Mr with their
    interpolation brackets and field resolutions, derived loop asymmetry, and
    warnings. Values remain in raw instrument units (Oe, emu) and row indices
    refer to the original parsed rows.
    """
    settings = DEFAULT_CONFIG if config is None else config

    if not isinstance(parsed, dict):
        raise HysteresisAnalysisError("Parsed input must be a dictionary.")
    if not isinstance(segment, dict):
        raise HysteresisAnalysisError("Segment must be a dictionary.")

    segment_type = segment.get("type")
    if segment_type != SEGMENT_TYPE_MH:
        raise HysteresisAnalysisError(
            f"Hysteresis analysis requires an '{SEGMENT_TYPE_MH}' segment, but the "
            f"supplied segment has type {segment_type!r}."
        )

    data = parsed.get("data")
    if not isinstance(data, dict) or not data:
        raise HysteresisAnalysisError("Parsed input has no 'data' columns.")

    field = _required_column(data, FIELD_ALIASES, "magnetic field")
    moment = _required_column(data, MOMENT_ALIASES, "moment")
    temperature = _lookup_column(data, TEMPERATURE_ALIASES)

    if len(field) != len(moment):
        raise HysteresisAnalysisError(
            "Magnetic field and moment columns have different lengths "
            f"({len(field)} and {len(moment)} rows). Refusing to analyze misaligned "
            "columns."
        )

    row_count = len(field)
    if row_count == 0:
        raise HysteresisAnalysisError("Parsed data contains no rows.")

    first_row = segment.get("start_index", 0)
    last_row = segment.get("end_index", row_count - 1)
    if not isinstance(first_row, int) or not isinstance(last_row, int):
        raise HysteresisAnalysisError(
            "Segment start_index and end_index must be integers."
        )

    if first_row < 0:
        raise HysteresisAnalysisError(
            f"Segment start_index {first_row} is negative."
        )
    if last_row < first_row:
        raise HysteresisAnalysisError(
            f"Segment end_index {last_row} is before start_index {first_row}."
        )
    if last_row >= row_count:
        raise HysteresisAnalysisError(
            f"Segment end_index {last_row} is outside the parsed data, which has "
            f"{row_count} rows (last valid index {row_count - 1})."
        )

    warnings: list[str] = []
    total_points = last_row - first_row + 1
    positions = [
        row
        for row in range(first_row, last_row + 1)
        if math.isfinite(field[row]) and math.isfinite(moment[row])
    ]

    ignored = total_points - len(positions)
    if ignored:
        warnings.append(
            f"{ignored} of {total_points} points in this segment have a non-finite "
            "field or moment and were ignored during analysis."
        )

    if len(positions) < settings.minimum_valid_points:
        raise HysteresisAnalysisError(
            f"Only {len(positions)} valid points in segment rows {first_row}-{last_row}; "
            f"at least {settings.minimum_valid_points} are required to analyze a "
            "hysteresis loop."
        )

    branches: list[dict[str, Any]] = []
    branch_spans: list[tuple[int, int, str]] = []
    for sign, start, end in _sweep_runs(field, positions, settings):
        point_count = end - start + 1
        direction = _direction_name(sign)
        if point_count < settings.minimum_branch_points:
            warnings.append(
                f"Ignored a {point_count}-point {direction}-field run at rows "
                f"{positions[start]}-{positions[end]}: too short to be treated as a "
                "hysteresis branch."
            )
            continue
        branches.append(
            {
                "direction": direction,
                "start_index": positions[start],
                "end_index": positions[end],
                "point_count": point_count,
                "field_start_Oe": field[positions[start]],
                "field_end_Oe": field[positions[end]],
            }
        )
        branch_spans.append((start, end, direction))

    if not branches:
        warnings.append(
            "No field sweep branch could be identified; the segment may be a setup or "
            "stabilization region rather than a hysteresis loop."
        )
    elif len(branches) == 1:
        warnings.append(
            f"Only one field sweep branch ({branches[0]['direction']}) was identified; "
            "branch-specific values are available for that branch only."
        )

    coercivity: dict[str, Optional[dict[str, Any]]] = {_NEGATIVE: None, _POSITIVE: None}
    remanence: dict[str, Optional[dict[str, Any]]] = {_NEGATIVE: None, _POSITIVE: None}

    for start, end, direction in branch_spans:
        _extract_branch_crossings(
            crossing_of=moment,
            interpolated_over=field,
            field=field,
            moment=moment,
            positions=positions,
            start=start,
            end=end,
            direction=direction,
            slots=coercivity,
            label="coercive field",
            warnings=warnings,
        )
        _extract_branch_crossings(
            crossing_of=field,
            interpolated_over=moment,
            field=field,
            moment=moment,
            positions=positions,
            start=start,
            end=end,
            direction=direction,
            slots=remanence,
            label="remanent moment",
            warnings=warnings,
        )

    for slots, label, names in (
        (coercivity, "coercive field", ("Hc_negative_Oe", "Hc_positive_Oe")),
        (remanence, "remanent moment", ("Mr_negative_emu", "Mr_positive_emu")),
    ):
        for key, name in zip((_NEGATIVE, _POSITIVE), names):
            if slots[key] is None:
                warnings.append(
                    f"No zero-crossing produced a {key} {label}; {name} is unavailable."
                )

    negative_hc = _slot_value(coercivity, _NEGATIVE)
    positive_hc = _slot_value(coercivity, _POSITIVE)
    if negative_hc is not None and positive_hc is not None:
        center_shift = (positive_hc + negative_hc) / 2.0
        half_width = (positive_hc - negative_hc) / 2.0
    else:
        center_shift = None
        half_width = None

    return {
        "segment_type": SEGMENT_TYPE_MH,
        "start_index": first_row,
        "end_index": last_row,
        "point_count": total_points,
        "valid_point_count": len(positions),
        "temperature_range_K": segment.get("temperature_range_K"),
        "mean_temperature_K": segment.get("mean_temperature_K"),
        "field_range_Oe": [
            min(field[row] for row in positions),
            max(field[row] for row in positions),
        ],
        "branches": branches,
        "Hc_negative_Oe": negative_hc,
        "Hc_positive_Oe": positive_hc,
        "Hc_negative_bracket": _slot_bracket(coercivity, _NEGATIVE),
        "Hc_positive_bracket": _slot_bracket(coercivity, _POSITIVE),
        "Hc_negative_resolution_Oe": _slot_resolution(coercivity, _NEGATIVE),
        "Hc_positive_resolution_Oe": _slot_resolution(coercivity, _POSITIVE),
        "Mr_negative_emu": _slot_value(remanence, _NEGATIVE),
        "Mr_positive_emu": _slot_value(remanence, _POSITIVE),
        "Mr_negative_bracket": _slot_bracket(remanence, _NEGATIVE),
        "Mr_positive_bracket": _slot_bracket(remanence, _POSITIVE),
        "coercive_center_shift_Oe": center_shift,
        "coercive_half_width_Oe": half_width,
        "units": {
            "field": "Oe",
            "moment": "emu",
            "temperature": "K" if temperature is not None else None,
        },
        "warnings": warnings,
        "config": settings,
    }
