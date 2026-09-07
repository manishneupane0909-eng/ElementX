"""
Parser for native Quantum Design / VersaLab MultiVu .DAT magnetometry files.

Ingestion only: reads header metadata and tabular measurement columns. Does not
compute Ms, Mr, Hc, Tc, or any derived magnetic properties.
"""

from __future__ import annotations

import csv
import math
import re
from typing import Any, Optional, Union

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "temperature": ("Temperature (K)",),
    "magnetic_field": ("Magnetic Field (Oe)",),
    "moment": ("Moment (emu)",),
}

# Canonical unit labels preserved from the file (no unit conversion).
COLUMN_UNITS: dict[str, str] = {
    "Temperature (K)": "K",
    "Magnetic Field (Oe)": "Oe",
    "Moment (emu)": "emu",
}

CellValue = Union[float, str]


class QuantumDesignParseError(ValueError):
    """Raised when a Quantum Design .DAT file cannot be parsed."""


def is_quantum_design_dat(text: str) -> bool:
    """
    Return True when the text contains Quantum Design [Header] and [Data] sections.
    """
    if not text or not text.strip():
        return False

    has_header = False
    has_data = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "[Header]":
            has_header = True
        elif line == "[Data]":
            has_data = True
        if has_header and has_data:
            return True
    return False


def _normalize_column_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def _find_column_index(column_names: list[str], aliases: tuple[str, ...]) -> Optional[int]:
    normalized = {_normalize_column_name(name): idx for idx, name in enumerate(column_names)}
    for alias in aliases:
        idx = normalized.get(_normalize_column_name(alias))
        if idx is not None:
            return idx
    return None


def _required_column_names(column_names: list[str]) -> set[str]:
    required: set[str] = set()
    for aliases in REQUIRED_COLUMNS.values():
        idx = _find_column_index(column_names, aliases)
        if idx is not None:
            required.add(column_names[idx])
    return required


def _parse_header(lines: list[str]) -> tuple[dict[str, Any], list[str]]:
    metadata: dict[str, Any] = {}
    warnings: list[str] = []
    in_header = False

    for raw_line in lines:
        line = raw_line.strip()
        if line == "[Header]":
            in_header = True
            continue
        if line == "[Data]":
            break
        if not in_header or not line or line.startswith(";"):
            continue

        if line.startswith("INFO,"):
            parts = line.split(",", 2)
            if len(parts) == 3:
                value, key = parts[1].strip(), parts[2].strip()
                if value:
                    metadata[key] = value
                continue

        if "," in line:
            key, value = line.split(",", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                metadata[key] = value

    if "SAMPLE_MASS" not in metadata:
        warnings.append("SAMPLE_MASS not found in file header.")

    return metadata, warnings


def _parse_float(value: str) -> float:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("empty value")
    return float(cleaned)


def _is_finite(value: float) -> bool:
    return math.isfinite(value)


def _parse_cell_value(cell: str, *, is_required: bool) -> CellValue:
    cleaned = cell.strip()
    if is_required:
        if not cleaned:
            return float("nan")
        try:
            return _parse_float(cleaned)
        except ValueError:
            return float("nan")

    if not cleaned:
        return ""
    try:
        return _parse_float(cleaned)
    except ValueError:
        return cleaned


def _instrument_from_metadata(metadata: dict[str, Any]) -> str:
    app_name = metadata.get("APPNAME")
    if isinstance(app_name, str) and app_name.strip():
        return app_name.strip()
    return "unknown"


def parse_quantum_design_dat(text: str) -> dict[str, Any]:
    """
    Parse a Quantum Design / VersaLab .DAT file into a structured dictionary.

    Returns
    -------
    dict with keys:
        instrument, file_type, metadata, columns, data, units, warnings

    Raises
    ------
    QuantumDesignParseError
        If the file is not recognized or required columns/values are missing.
    """
    if not is_quantum_design_dat(text):
        raise QuantumDesignParseError(
            "File is not a recognized Quantum Design .DAT export "
            "(expected [Header] and [Data] sections)."
        )

    lines = text.splitlines()
    metadata, warnings = _parse_header(lines)

    data_started = False
    column_names: list[str] = []
    row_values: list[list[str]] = []

    for raw_line in lines:
        line = raw_line.strip()
        if line == "[Data]":
            data_started = True
            continue
        if not data_started:
            continue
        if not line or line.startswith(";"):
            continue
        if not column_names:
            column_names = [col.strip() for col in next(csv.reader([line]))]
            continue
        row_values.append(next(csv.reader([line])))

    if not column_names:
        raise QuantumDesignParseError("No column header row found after [Data].")

    column_indices = {
        key: _find_column_index(column_names, aliases)
        for key, aliases in REQUIRED_COLUMNS.items()
    }
    missing = [key for key, idx in column_indices.items() if idx is None]
    if missing:
        raise QuantumDesignParseError(
            "Required measurement columns missing from [Data] header: "
            + ", ".join(missing)
            + f". Available columns: {column_names}"
        )

    required_names = _required_column_names(column_names)
    parsed_data: dict[str, list[CellValue]] = {name: [] for name in column_names}
    for row in row_values:
        if len(row) < len(column_names):
            row = row + [""] * (len(column_names) - len(row))
        for idx, col_name in enumerate(column_names):
            cell = row[idx] if idx < len(row) else ""
            parsed_data[col_name].append(
                _parse_cell_value(cell, is_required=col_name in required_names)
            )

    for logical_name, col_key in (
        ("temperature", "temperature"),
        ("magnetic_field", "magnetic_field"),
        ("moment", "moment"),
    ):
        col_name = column_names[column_indices[col_key]]  # type: ignore[index]
        values = parsed_data[col_name]
        if not values:
            raise QuantumDesignParseError(f"No data rows found for {logical_name}.")
        finite_values = [v for v in values if isinstance(v, float) and _is_finite(v)]
        if not finite_values:
            raise QuantumDesignParseError(
                f"Column '{col_name}' contains no finite numerical values."
            )
        if len(finite_values) != len(values):
            warnings.append(
                f"Column '{col_name}' contains non-finite or empty values "
                f"({len(values) - len(finite_values)} of {len(values)} rows)."
            )

    units = {
        col: COLUMN_UNITS.get(col, "unknown")
        for col in column_names
        if col in COLUMN_UNITS
    }

    return {
        "instrument": _instrument_from_metadata(metadata),
        "file_type": "quantum_design_dat",
        "metadata": metadata,
        "columns": column_names,
        "data": parsed_data,
        "units": units,
        "warnings": warnings,
    }
