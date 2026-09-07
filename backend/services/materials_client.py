"""
Materials Project API client for formula-based magnetic and structural lookups.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from pydantic import BaseModel, Field

ORDERING_LABELS: dict[str, str] = {
    "FM": "ferromagnetic",
    "FiM": "ferrimagnetic",
    "AFM": "antiferromagnetic",
    "NM": "non-magnetic",
    "PM": "paramagnetic",
    "Unknown": "unknown",
}


class MaterialsClientError(Exception):
    """Base error for Materials Project queries."""


class MaterialsAPIKeyError(MaterialsClientError):
    """Raised when the Materials Project API key is missing or invalid."""


class MaterialsNotFoundError(MaterialsClientError):
    """Raised when no entry matches the requested formula."""


class SymmetryInfo(BaseModel):
    crystal_system: Optional[str] = None
    space_group_symbol: Optional[str] = None
    space_group_number: Optional[int] = None


class FormulaQueryResult(BaseModel):
    material_id: str
    formula: str
    symmetry: SymmetryInfo
    total_magnetic_moment: Optional[float] = Field(
        None,
        description="Total magnetization in μB per formula unit (Materials Project convention).",
    )
    magnetic_ordering: Optional[str] = Field(
        None,
        description="Human-readable magnetic ordering (ferromagnetic, ferrimagnetic, etc.).",
    )
    magnetic_ordering_code: Optional[str] = Field(
        None,
        description="Materials Project ordering code (FM, FiM, AFM, NM, ...).",
    )
    energy_above_hull: Optional[float] = None
    unit_cell_volume: Optional[float] = Field(
        None,
        description="Crystallographic unit-cell volume in Å³.",
    )
    num_matches: int = 1


def _ordering_to_label(ordering: Any) -> tuple[Optional[str], Optional[str]]:
    if ordering is None:
        return None, None

    code = getattr(ordering, "value", None) or str(ordering)
    code = code.strip()
    if not code or code.lower() == "none":
        return None, None

    label = ORDERING_LABELS.get(code, code.replace("_", " ").lower())
    return label, code


def _extract_symmetry(doc: Any) -> SymmetryInfo:
    symmetry = getattr(doc, "symmetry", None)
    if symmetry is None:
        return SymmetryInfo()

    return SymmetryInfo(
        crystal_system=getattr(symmetry, "crystal_system", None),
        space_group_symbol=getattr(symmetry, "symbol", None),
        space_group_number=getattr(symmetry, "number", None),
    )


def _pick_magnetization(doc: Any) -> Optional[float]:
    for attr in (
        "total_magnetization_normalized_formula_units",
        "total_magnetization",
    ):
        value = getattr(doc, attr, None)
        if value is not None:
            return float(value)
    return None


class MaterialsClient:
    """Query Materials Project for structural and magnetic properties by formula."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("MP_API_KEY") or os.getenv("MATERIALS_PROJECT_API_KEY")

    def _require_api_key(self) -> str:
        if not self.api_key:
            raise MaterialsAPIKeyError(
                "Materials Project API key not configured. "
                "Set MP_API_KEY (or MATERIALS_PROJECT_API_KEY) in the environment."
            )
        return self.api_key

    def query_formula(self, formula: str) -> FormulaQueryResult:
        """
        Look up the most stable Materials Project entry for a chemical formula.

        Returns structural symmetry, total magnetic moment, and magnetic ordering.
        """
        normalized = formula.strip()
        if not normalized:
            raise ValueError("Formula must not be empty.")

        api_key = self._require_api_key()

        try:
            from mp_api.client import MPRester
        except ImportError as exc:
            raise MaterialsClientError(
                "mp-api is not installed. Install backend requirements with: pip install -r requirements.txt"
            ) from exc

        fields = [
            "material_id",
            "formula_pretty",
            "symmetry",
            "total_magnetization",
            "total_magnetization_normalized_formula_units",
            "ordering",
            "energy_above_hull",
            "volume",
        ]

        try:
            with MPRester(api_key) as mpr:
                docs = mpr.materials.summary.search(formula=normalized, fields=fields)
        except Exception as exc:
            message = str(exc).lower()
            if "api key" in message or "unauthorized" in message or "401" in message:
                raise MaterialsAPIKeyError("Invalid or unauthorized Materials Project API key.") from exc
            raise MaterialsClientError(f"Materials Project query failed: {exc}") from exc

        if not docs:
            raise MaterialsNotFoundError(f"No Materials Project entry found for formula '{normalized}'.")

        ranked = sorted(
            docs,
            key=lambda doc: (
                getattr(doc, "energy_above_hull", None) is None,
                getattr(doc, "energy_above_hull", float("inf")),
            ),
        )
        best = ranked[0]

        ordering_label, ordering_code = _ordering_to_label(getattr(best, "ordering", None))
        magnetic_moment = _pick_magnetization(best)

        if ordering_label is None or magnetic_moment is None:
            try:
                with MPRester(api_key) as mpr:
                    mag_docs = mpr.materials.magnetism.search(
                        material_ids=[best.material_id],
                        fields=["ordering", "total_magnetization", "total_magnetization_normalized_formula_units"],
                    )
                if mag_docs:
                    mag = mag_docs[0]
                    if ordering_label is None:
                        ordering_label, ordering_code = _ordering_to_label(getattr(mag, "ordering", None))
                    if magnetic_moment is None:
                        magnetic_moment = _pick_magnetization(mag)
            except Exception:
                # Summary data is sufficient when magnetism endpoint is unavailable.
                pass

        return FormulaQueryResult(
            material_id=str(best.material_id),
            formula=getattr(best, "formula_pretty", None) or normalized,
            symmetry=_extract_symmetry(best),
            total_magnetic_moment=magnetic_moment,
            magnetic_ordering=ordering_label,
            magnetic_ordering_code=ordering_code,
            energy_above_hull=getattr(best, "energy_above_hull", None),
            unit_cell_volume=getattr(best, "volume", None),
            num_matches=len(docs),
        )
