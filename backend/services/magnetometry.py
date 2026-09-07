"""
Measurement segmentation for parsed Quantum Design magnetometry data.

Splits a combined .DAT acquisition into distinct measurement sequences and
labels each one as M-H (field sweep at approximately fixed temperature), M-T
(temperature sweep at approximately fixed field), or "unknown" when the
evidence is insufficient.

Identification only: this module does not compute Ms, Mr, Hc, Tc, BHmax, or any
magnetic normalization.

Classification is driven by relative behavior -- which quantity sweeps and which
is approximately held -- rather than by absolute setpoint values or filenames.
The numeric tolerances live in :class:`SegmentationConfig` so they can be tuned
per instrument or, in a later version, estimated from the measurement itself.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

TEMPERATURE_ALIASES = ("Temperature (K)",)
FIELD_ALIASES = ("Magnetic Field (Oe)",)
MOMENT_ALIASES = ("Moment (emu)",)
TIME_ALIASES = ("Time Stamp (sec)",)
COMMENT_ALIASES = ("Comment",)

TYPE_MH = "M-H"
TYPE_MT = "M-T"
TYPE_UNKNOWN = "unknown"

_SWEEP_FIELD = "H"
_SWEEP_TEMPERATURE = "T"


class MagnetometrySegmentationError(ValueError):
    """Raised when parsed data cannot be segmented into measurement sequences."""


@dataclass(frozen=True)
class SegmentationConfig:
    """
    Heuristic tolerances for measurement segmentation.

    Every value here is a **v1 heuristic default**, not a physical constant.
    They encode typical Quantum Design VSM stability and step sizes, and a
    later version is expected to estimate them from the measurement itself
    (for example from the observed noise floor of a held quantity) instead of
    relying on these fixed numbers. Callers with a differently behaved
    instrument should pass their own configuration.

    Attributes
    ----------
    temperature_noise_tolerance_K:
        Temperature spread treated as "approximately held constant". Used to
        normalize the temperature span so it can be compared against the field
        span on a common scale.
    field_noise_tolerance_Oe:
        Field spread treated as "approximately held constant", used the same way
        as ``temperature_noise_tolerance_K``.
    temperature_variation_threshold_K:
        Minimum temperature span for a segment to count as temperature-sweeping.
    field_variation_threshold_Oe:
        Minimum field span for a segment to count as field-sweeping.
    setpoint_change_threshold_K:
        Temperature step that separates consecutive M-H loops. This is a tuning
        knob, not a universal constant: it must sit above in-loop temperature
        drift and below the smallest intended spacing between loops.
    field_setpoint_change_threshold_Oe:
        Absolute field step that separates consecutive M-T runs.
    field_setpoint_change_fraction:
        Relative field step used alongside the absolute threshold, so that high
        bias fields tolerate proportionally larger drift.
    window_points:
        Width, in valid rows, of the centered window used to decide which
        quantity is sweeping locally.
    setpoint_confirmation_points:
        Number of following rows that must agree before a setpoint change is
        accepted, which suppresses single-row glitches.
    minimum_segment_points:
        Segments shorter than this are merged into a neighbour rather than
        reported as their own measurement sequence.
    """

    temperature_noise_tolerance_K: float = 2.0
    field_noise_tolerance_Oe: float = 50.0
    temperature_variation_threshold_K: float = 5.0
    field_variation_threshold_Oe: float = 200.0
    setpoint_change_threshold_K: float = 5.0
    field_setpoint_change_threshold_Oe: float = 100.0
    field_setpoint_change_fraction: float = 0.05
    window_points: int = 9
    setpoint_confirmation_points: int = 3
    minimum_segment_points: int = 8

    def __post_init__(self) -> None:
        strictly_positive = (
            "temperature_noise_tolerance_K",
            "field_noise_tolerance_Oe",
            "temperature_variation_threshold_K",
            "field_variation_threshold_Oe",
            "setpoint_change_threshold_K",
            "field_setpoint_change_threshold_Oe",
        )
        for name in strictly_positive:
            if getattr(self, name) <= 0:
                raise MagnetometrySegmentationError(f"{name} must be positive.")

        if self.field_setpoint_change_fraction < 0:
            raise MagnetometrySegmentationError(
                "field_setpoint_change_fraction must not be negative."
            )

        minimums = {
            "window_points": 3,
            "setpoint_confirmation_points": 1,
            "minimum_segment_points": 1,
        }
        for name, minimum in minimums.items():
            if getattr(self, name) < minimum:
                raise MagnetometrySegmentationError(
                    f"{name} must be at least {minimum}."
                )


DEFAULT_CONFIG = SegmentationConfig()


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


def _numeric_column(data: dict[str, Any], aliases: tuple[str, ...], label: str) -> list[float]:
    column = _lookup_column(data, aliases)
    if column is None:
        raise MagnetometrySegmentationError(
            f"Required column for {label} not found in parsed data. "
            f"Available columns: {sorted(data)}"
        )
    return [_as_float(value) for value in column]


def _span(values: list[float]) -> float:
    return max(values) - min(values)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sweep_labels(
    temperature: list[float],
    field: list[float],
    valid: list[int],
    config: SegmentationConfig,
) -> list[Optional[str]]:
    """Label each valid row by which quantity is sweeping in its local window."""
    labels: list[Optional[str]] = []
    half = config.window_points // 2
    total = len(valid)

    for position in range(total):
        window = valid[max(0, position - half) : min(total, position + half + 1)]
        temperature_score = (
            _span([temperature[i] for i in window]) / config.temperature_noise_tolerance_K
        )
        field_score = _span([field[i] for i in window]) / config.field_noise_tolerance_Oe

        if temperature_score < 1.0 and field_score < 1.0:
            labels.append(None)
        elif field_score >= temperature_score:
            labels.append(_SWEEP_FIELD)
        else:
            labels.append(_SWEEP_TEMPERATURE)

    return _fill_gaps(labels)


def _fill_gaps(labels: list[Optional[str]]) -> list[Optional[str]]:
    """Attach unlabeled (locally flat) rows to the nearest labeled neighbour."""
    known = [label for label in labels if label is not None]
    if not known:
        return list(labels)

    # Rows before the first label adopt it; every later gap inherits from the left.
    carried = known[0]
    filled: list[Optional[str]] = []
    for label in labels:
        if label is not None:
            carried = label
        filled.append(carried)
    return filled


def _normalized_step(
    temperature: list[float],
    field: list[float],
    previous_row: int,
    row: int,
    config: SegmentationConfig,
) -> float:
    return max(
        abs(temperature[row] - temperature[previous_row])
        / config.temperature_noise_tolerance_K,
        abs(field[row] - field[previous_row]) / config.field_noise_tolerance_Oe,
    )


def _refine_boundary(
    temperature: list[float],
    field: list[float],
    valid: list[int],
    boundary: int,
    config: SegmentationConfig,
) -> int:
    """Snap a window-smeared boundary onto the row with the largest local step."""
    half = config.window_points // 2
    lowest = max(1, boundary - half)
    highest = min(len(valid) - 1, boundary + half)

    best_position = boundary
    best_step = -1.0
    for position in range(lowest, highest + 1):
        step = _normalized_step(
            temperature, field, valid[position - 1], valid[position], config
        )
        if step > best_step:
            best_step = step
            best_position = position
    return best_position


def _setpoint_boundaries(
    held: list[float],
    valid: list[int],
    start: int,
    end: int,
    threshold_for: Callable[[float], float],
    config: SegmentationConfig,
) -> list[int]:
    """Find positions where the held quantity moves to a new, persistent setpoint."""
    boundaries: list[int] = []
    reference = held[valid[start]]

    position = start + 1
    while position < end:
        threshold = threshold_for(reference)
        if abs(held[valid[position]] - reference) <= threshold:
            position += 1
            continue

        confirmed = all(
            abs(held[valid[ahead]] - reference) > threshold
            for ahead in range(
                position, min(end, position + config.setpoint_confirmation_points)
            )
        )
        if confirmed:
            boundaries.append(position)
            reference = held[valid[position]]
        position += 1

    return boundaries


def _comment_boundaries(comments: Optional[list[Any]], valid: list[int]) -> list[int]:
    """Treat a change in non-empty instrument annotation as a boundary hint."""
    if comments is None:
        return []

    boundaries: list[int] = []
    previous = ""
    for position, row in enumerate(valid):
        if row >= len(comments):
            break
        value = comments[row]
        text = value.strip() if isinstance(value, str) else ""
        if text and text != previous:
            if position > 0:
                boundaries.append(position)
            previous = text
    return boundaries


def _merge_short_blocks(
    blocks: list[tuple[int, int]], config: SegmentationConfig
) -> list[tuple[int, int]]:
    if len(blocks) <= 1:
        return blocks

    merged = [blocks[0]]
    for start, end in blocks[1:]:
        previous_start, previous_end = merged[-1]
        too_short = end - start < config.minimum_segment_points
        previous_too_short = previous_end - previous_start < config.minimum_segment_points
        if too_short or previous_too_short:
            merged[-1] = (previous_start, end)
        else:
            merged.append((start, end))
    return merged


def _classify(
    temperature_span: float,
    field_span: float,
    config: SegmentationConfig,
) -> tuple[str, float, list[str]]:
    """Classify a segment from the relative behavior of temperature and field."""
    temperature_score = temperature_span / config.temperature_variation_threshold_K
    field_score = field_span / config.field_variation_threshold_Oe
    temperature_varies = temperature_score >= 1.0
    field_varies = field_score >= 1.0

    if not temperature_varies and not field_varies:
        return (
            TYPE_UNKNOWN,
            0.0,
            [
                "Neither temperature nor magnetic field varies enough to identify "
                "a sweep direction."
            ],
        )

    if temperature_varies and field_varies:
        return (
            TYPE_UNKNOWN,
            0.0,
            [
                "Temperature and magnetic field both vary substantially; "
                "sweep type is ambiguous."
            ],
        )

    # Exactly one quantity sweeps here, so the winning score is at least 1.0.
    total = temperature_score + field_score
    if temperature_varies:
        return TYPE_MT, round(temperature_score / total, 4), []

    return TYPE_MH, round(field_score / total, 4), []


def segment_measurements(
    parsed: dict[str, Any],
    config: Optional[SegmentationConfig] = None,
) -> dict[str, Any]:
    """
    Identify distinct measurement sequences in parsed Quantum Design data.

    Parameters
    ----------
    parsed:
        Output of ``parse_quantum_design_dat``, or any mapping with a ``data``
        dictionary containing temperature, magnetic field and moment columns.
    config:
        Heuristic tolerances. Defaults to :data:`DEFAULT_CONFIG`.

    Returns
    -------
    dict with keys ``segments``, ``warnings`` and ``config``. Segment
    ``start_index`` and ``end_index`` always refer to rows of the original
    parsed data, including rows whose values were non-finite.
    """
    if not isinstance(parsed, dict):
        raise MagnetometrySegmentationError("Parsed input must be a dictionary.")

    settings = DEFAULT_CONFIG if config is None else config

    data = parsed.get("data")
    if not isinstance(data, dict) or not data:
        raise MagnetometrySegmentationError("Parsed input has no 'data' columns.")

    temperature = _numeric_column(data, TEMPERATURE_ALIASES, "temperature")
    field = _numeric_column(data, FIELD_ALIASES, "magnetic field")
    moment = _numeric_column(data, MOMENT_ALIASES, "moment")
    timestamps = _lookup_column(data, TIME_ALIASES)
    comments = _lookup_column(data, COMMENT_ALIASES)

    temperature_len = len(temperature)
    field_len = len(field)
    moment_len = len(moment)
    if not (temperature_len == field_len == moment_len):
        raise MagnetometrySegmentationError(
            "Temperature, magnetic field, and moment columns have different lengths "
            f"({temperature_len}, {field_len}, and {moment_len} rows). Misaligned "
            "columns will not be segmented."
        )

    row_count = temperature_len
    if row_count == 0:
        raise MagnetometrySegmentationError("Parsed data contains no rows.")

    warnings: list[str] = []
    if timestamps is None:
        warnings.append("Time Stamp column not present; segment durations unavailable.")
    if comments is None:
        warnings.append("Comment column not present; annotation hints unavailable.")

    valid = [
        row
        for row in range(row_count)
        if math.isfinite(temperature[row]) and math.isfinite(field[row])
    ]
    invalid_count = row_count - len(valid)
    if invalid_count:
        warnings.append(
            f"{invalid_count} of {row_count} rows have non-finite temperature or field "
            "and were excluded from statistics but retained in segment index ranges."
        )

    invalid_moments = sum(1 for row in range(row_count) if not math.isfinite(moment[row]))
    if invalid_moments:
        warnings.append(
            f"{invalid_moments} of {row_count} rows have a non-finite moment; "
            "rows were retained."
        )

    if not valid:
        return {
            "segments": [
                _build_segment(
                    0,
                    row_count - 1,
                    [],
                    temperature,
                    field,
                    moment,
                    timestamps,
                    settings,
                )
            ],
            "warnings": warnings
            + ["No rows with finite temperature and field; segmentation skipped."],
            "config": settings,
        }

    blocks = _build_blocks(temperature, field, valid, comments, settings)

    segments: list[dict[str, Any]] = []
    for order, (start, end) in enumerate(blocks):
        start_row = 0 if order == 0 else valid[start]
        end_row = (
            row_count - 1
            if order == len(blocks) - 1
            else valid[blocks[order + 1][0]] - 1
        )
        segments.append(
            _build_segment(
                start_row,
                end_row,
                valid[start:end],
                temperature,
                field,
                moment,
                timestamps,
                settings,
            )
        )

    return {"segments": segments, "warnings": warnings, "config": settings}


def _build_blocks(
    temperature: list[float],
    field: list[float],
    valid: list[int],
    comments: Optional[list[Any]],
    config: SegmentationConfig,
) -> list[tuple[int, int]]:
    """Return (start, end) half-open ranges in valid-row position space."""
    labels = _sweep_labels(temperature, field, valid, config)

    regime_boundaries = [
        position
        for position in range(1, len(valid))
        if labels[position] != labels[position - 1]
    ]
    boundaries = {
        _refine_boundary(temperature, field, valid, position, config)
        for position in regime_boundaries
    }
    boundaries.update(_comment_boundaries(comments, valid))

    edges = [0] + sorted(boundaries) + [len(valid)]

    def field_threshold(reference: float) -> float:
        return max(
            config.field_setpoint_change_threshold_Oe,
            abs(reference) * config.field_setpoint_change_fraction,
        )

    def temperature_threshold(_reference: float) -> float:
        return config.setpoint_change_threshold_K

    blocks: list[tuple[int, int]] = []
    for start, end in zip(edges, edges[1:]):
        if end <= start:
            continue
        if labels[start] == _SWEEP_FIELD:
            held, threshold_for = temperature, temperature_threshold
        else:
            held, threshold_for = field, field_threshold

        inner = _setpoint_boundaries(held, valid, start, end, threshold_for, config)
        sub_edges = [start] + inner + [end]
        for sub_start, sub_end in zip(sub_edges, sub_edges[1:]):
            if sub_end > sub_start:
                blocks.append((sub_start, sub_end))

    return _merge_short_blocks(blocks, config)


def _build_segment(
    start_row: int,
    end_row: int,
    valid_rows: list[int],
    temperature: list[float],
    field: list[float],
    moment: list[float],
    timestamps: Optional[list[Any]],
    config: SegmentationConfig,
) -> dict[str, Any]:
    point_count = end_row - start_row + 1

    if not valid_rows:
        return {
            "type": TYPE_UNKNOWN,
            "start_index": start_row,
            "end_index": end_row,
            "point_count": point_count,
            "valid_point_count": 0,
            "temperature_range_K": None,
            "field_range_Oe": None,
            "mean_temperature_K": None,
            "mean_field_Oe": None,
            "duration_sec": None,
            "confidence": 0.0,
            "warnings": ["Segment contains no rows with finite temperature and field."],
            "data": _empty_measured_series(),
        }

    temperatures = [temperature[row] for row in valid_rows]
    fields = [field[row] for row in valid_rows]

    temperature_range = [min(temperatures), max(temperatures)]
    field_range = [min(fields), max(fields)]
    segment_type, confidence, segment_warnings = _classify(
        temperature_range[1] - temperature_range[0],
        field_range[1] - field_range[0],
        config,
    )

    if len(valid_rows) < point_count:
        segment_warnings.append(
            f"{point_count - len(valid_rows)} of {point_count} rows in this segment "
            "were excluded from statistics because of non-finite values."
        )

    invalid_moments = sum(1 for row in valid_rows if not math.isfinite(moment[row]))
    if invalid_moments:
        segment_warnings.append(
            f"{invalid_moments} rows in this segment have a non-finite moment."
        )

    return {
        "type": segment_type,
        "start_index": start_row,
        "end_index": end_row,
        "point_count": point_count,
        "valid_point_count": len(valid_rows),
        "temperature_range_K": temperature_range,
        "field_range_Oe": field_range,
        "mean_temperature_K": _mean(temperatures),
        "mean_field_Oe": _mean(fields),
        "duration_sec": _duration(timestamps, valid_rows),
        "confidence": confidence,
        "warnings": segment_warnings,
        "data": _measured_series(valid_rows, temperature, field, moment),
    }


def _empty_measured_series() -> dict[str, list[Any]]:
    return {
        "temperature_K": [],
        "field_Oe": [],
        "moment_emu": [],
        "source_index": [],
    }


def _measured_series(
    valid_rows: list[int],
    temperature: list[float],
    field: list[float],
    moment: list[float],
) -> dict[str, list[Any]]:
    """
    Return aligned measured points for one segment in original acquisition order.

    Rows already classified as valid by segmentation (finite temperature and
    field) are included. A non-finite moment is omitted so the JSON series
    stays finite; no interpolation, sorting, or synthetic points are added.
    """
    temperature_K: list[float] = []
    field_Oe: list[float] = []
    moment_emu: list[float] = []
    source_index: list[int] = []

    for row in valid_rows:
        t_value = temperature[row]
        h_value = field[row]
        m_value = moment[row]
        if not (
            math.isfinite(t_value)
            and math.isfinite(h_value)
            and math.isfinite(m_value)
        ):
            continue
        temperature_K.append(t_value)
        field_Oe.append(h_value)
        moment_emu.append(m_value)
        source_index.append(row)

    return {
        "temperature_K": temperature_K,
        "field_Oe": field_Oe,
        "moment_emu": moment_emu,
        "source_index": source_index,
    }


def _duration(timestamps: Optional[list[Any]], valid_rows: list[int]) -> Optional[float]:
    if timestamps is None:
        return None

    times: list[float] = []
    for row in valid_rows:
        if row >= len(timestamps):
            break
        value = _as_float(timestamps[row])
        if math.isfinite(value):
            times.append(value)

    if len(times) < 2:
        return None
    return max(times) - min(times)
