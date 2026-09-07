"""
CIF (Crystallographic Information File) parsing utilities using pymatgen.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from pydantic import BaseModel, Field


class LatticeParameters(BaseModel):
    a: float = Field(..., description="Lattice parameter a (Å)")
    b: float = Field(..., description="Lattice parameter b (Å)")
    c: float = Field(..., description="Lattice parameter c (Å)")
    alpha: float = Field(..., description="Lattice angle α (degrees)")
    beta: float = Field(..., description="Lattice angle β (degrees)")
    gamma: float = Field(..., description="Lattice angle γ (degrees)")


class CifParseResult(BaseModel):
    formula: str
    num_sites: int
    lattice: LatticeParameters
    volume: float = Field(..., description="Unit-cell volume (Å³)")
    crystal_system: str
    space_group_symbol: Optional[str] = None
    space_group_number: Optional[int] = None
    density: float = Field(..., description="Theoretical density (g/cm³)")
    filename: Optional[str] = None


class CifParserError(Exception):
    """Raised when a CIF file cannot be parsed."""


def _parse_structures_from_text(cif_text: str):
    from pymatgen.io.cif import CifParser

    # pymatgen accepts file paths; write to a temp file for reliable parsing.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cif", delete=False, encoding="utf-8") as handle:
        handle.write(cif_text)
        temp_path = handle.name

    try:
        parser = CifParser(temp_path)
        structures = parser.parse_structures(primitive=False)
    finally:
        os.unlink(temp_path)

    if not structures:
        raise CifParserError("CIF file did not contain any valid crystal structures.")

    return structures


def parse_cif_bytes(content: bytes, filename: Optional[str] = None) -> CifParseResult:
    """
    Parse an uploaded CIF file and return lattice, symmetry, and density information.
    """
    if not content or not content.strip():
        raise CifParserError("Uploaded CIF file is empty.")

    try:
        cif_text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CifParserError("CIF file must be UTF-8 encoded text.") from exc

    try:
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
    except ImportError as exc:
        raise CifParserError(
            "pymatgen is not installed. Install backend requirements with: pip install -r requirements.txt"
        ) from exc

    try:
        structures = _parse_structures_from_text(cif_text)
    except CifParserError:
        raise
    except Exception as exc:
        raise CifParserError(f"Failed to parse CIF structure: {exc}") from exc

    structure = structures[0]
    lattice = structure.lattice

    try:
        analyzer = SpacegroupAnalyzer(structure, symprec=0.1)
        crystal_system = analyzer.get_crystal_system()
        space_group_symbol = analyzer.get_space_group_symbol()
        space_group_number = analyzer.get_space_group_number()
    except Exception:
        crystal_system = "unknown"
        space_group_symbol = None
        space_group_number = None

    try:
        density = float(structure.density)
    except Exception as exc:
        raise CifParserError(f"Could not compute theoretical density: {exc}") from exc

    return CifParseResult(
        formula=structure.composition.reduced_formula,
        num_sites=len(structure),
        lattice=LatticeParameters(
            a=round(lattice.a, 6),
            b=round(lattice.b, 6),
            c=round(lattice.c, 6),
            alpha=round(lattice.alpha, 6),
            beta=round(lattice.beta, 6),
            gamma=round(lattice.gamma, 6),
        ),
        volume=round(lattice.volume, 6),
        crystal_system=crystal_system,
        space_group_symbol=space_group_symbol,
        space_group_number=space_group_number,
        density=round(density, 6),
        filename=filename,
    )
