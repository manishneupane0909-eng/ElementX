"""
Permanent-magnet domain physics for ElementX.

This module implements supply-chain criticality scoring and first-principles
estimates of saturation magnetization and maximum energy product from Materials
Project magnetic moments and unit-cell volumes.

Unit conventions
----------------
* Magnetic moment: Bohr magnetons per formula unit (μB/f.u.), as returned by MP.
* Volume: cubic ångströms (Å³) for the crystallographic unit cell.
* Saturation magnetization (Ms): tesla (T), reported as μ₀M for M in A/m.
* Maximum energy product ((BH)max): kJ/m³ and MGOe (1 MGOe = 7.958 kJ/m³).
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

# SI constants (CODATA 2022)
MU0 = 4.0 * math.pi * 1e-7  # vacuum permeability [H/m = N/A²]
MU_B = 9.2740100783e-24  # Bohr magneton [J/T = A·m²]
ANGSTROM3_TO_M3 = 1e-30  # (1 Å)³ → m³
MGOE_TO_KJ_M3 = 7.958  # 1 MGOe = 7.958 kJ/m³

# Supply-chain criticality weight per element (0 = abundant/sustainable, 100 = severe risk).
# Heavy rare-earth elements carry maximum penalty per DOE/USGS critical-materials guidance.
ELEMENT_CRITICALITY: dict[str, float] = {
    # Heavy / light rare earths — maximum or near-maximum penalty
    "Nd": 100.0,
    "Dy": 100.0,
    "Sm": 100.0,
    "Pr": 100.0,
    "Tb": 95.0,
    "Gd": 90.0,
    "Ho": 92.0,
    "Er": 92.0,
    "Tm": 90.0,
    "Yb": 88.0,
    "Lu": 85.0,
    "La": 80.0,
    "Ce": 78.0,
    "Eu": 88.0,
    "Y": 75.0,
    "Sc": 70.0,
    # Abundant transition metals & sustainable magnet candidates — low penalty
    "Fe": 8.0,
    "Co": 12.0,
    "Ni": 15.0,
    "N": 5.0,
    "Al": 5.0,
    "Mn": 10.0,
    "Bi": 12.0,
    # Common alloying / interstitial elements
    "B": 22.0,
    "C": 18.0,
    "Cu": 25.0,
    "Zn": 20.0,
    "Ga": 30.0,
    "Si": 12.0,
    "P": 15.0,
    "S": 15.0,
    "Mo": 35.0,
    "W": 40.0,
    "V": 28.0,
    "Cr": 22.0,
    "Nb": 32.0,
    "Zr": 30.0,
    "Hf": 38.0,
    "Ta": 40.0,
    "Ti": 18.0,
}

DEFAULT_ELEMENT_CRITICALITY = 45.0
HIGH_RISK_THRESHOLD = 70.0

_FORMULA_TOKEN_RE = re.compile(r"([A-Z][a-z]?)(\d+(?:\.\d+)?|\.\d+)?")


def parse_formula_composition(formula: str) -> dict[str, float]:
    """
    Parse a chemical formula into an element → stoichiometry mapping.

    Supports integer and decimal subscripts (e.g. ``Mn1.5In0.5Sb``).
    """
    normalized = formula.strip()
    if not normalized:
        raise ValueError("Formula must not be empty.")

    composition: dict[str, float] = {}
    for match in _FORMULA_TOKEN_RE.finditer(normalized):
        element = match.group(1)
        count_text = match.group(2)
        count = float(count_text) if count_text else 1.0
        if count <= 0:
            raise ValueError(f"Invalid stoichiometry for {element}: '{count_text}'")
        composition[element] = composition.get(element, 0.0) + count

    if not composition:
        raise ValueError(f"Could not parse any elements from formula '{formula}'.")

    return composition


def calculate_criticality_score(formula: str) -> dict[str, Any]:
    """
    Compute a Supply Chain Criticality Score (0–100) for a permanent-magnet formula.

    The score is a mole-fraction-weighted average of per-element criticality
    weights. Heavy rare-earth elements (Nd, Dy, Sm, Pr) receive the maximum
    penalty (100). Abundant, sustainable magnet constituents (Fe, Co, Ni, N, Al,
    Mn, Bi) receive low weights (5–15), reflecting lower geopolitical and
    extraction risk.

    Parameters
    ----------
    formula:
        Chemical formula string (e.g. ``"Nd2Fe14B"``).

    Returns
    -------
    dict
        ``total_score`` (0–100, rounded to 2 decimals),
        ``risk_level`` (qualitative band),
        ``high_risk_components`` (elements above the high-risk threshold),
        ``element_breakdown`` (per-element mole fraction and contribution).
    """
    composition = parse_formula_composition(formula)
    total_amount = sum(composition.values())
    if total_amount <= 0:
        raise ValueError("Formula composition must contain positive stoichiometry.")

    element_breakdown: list[dict[str, Any]] = []
    weighted_sum = 0.0

    for element, amount in sorted(composition.items()):
        mole_fraction = amount / total_amount
        element_score = ELEMENT_CRITICALITY.get(element, DEFAULT_ELEMENT_CRITICALITY)
        contribution = mole_fraction * element_score
        weighted_sum += contribution

        element_breakdown.append(
            {
                "element": element,
                "stoichiometry": amount,
                "mole_fraction": round(mole_fraction, 6),
                "element_criticality": element_score,
                "contribution": round(contribution, 4),
            }
        )

    total_score = round(min(max(weighted_sum, 0.0), 100.0), 2)

    high_risk_components = [
        {
            "element": item["element"],
            "mole_fraction": item["mole_fraction"],
            "element_criticality": item["element_criticality"],
            "contribution": item["contribution"],
        }
        for item in element_breakdown
        if item["element_criticality"] >= HIGH_RISK_THRESHOLD
    ]
    high_risk_components.sort(key=lambda row: row["contribution"], reverse=True)

    if total_score >= 75:
        risk_level = "critical"
    elif total_score >= 50:
        risk_level = "elevated"
    elif total_score >= 25:
        risk_level = "moderate"
    else:
        risk_level = "low"

    return {
        "formula": formula.strip(),
        "total_score": total_score,
        "risk_level": risk_level,
        "high_risk_components": high_risk_components,
        "element_breakdown": element_breakdown,
    }


def calculate_theoretical_limits(
    magnetic_moment: float,
    volume: float,
    formula_units_per_cell: int = 1,
) -> dict[str, Any]:
    """
    Estimate theoretical saturation magnetization and (BH)max upper bounds.

    Saturation magnetization
    ------------------------
    Given total magnetic moment ``m`` in μB per formula unit and unit-cell
    volume ``V_cell`` in Å³, the magnetization magnitude is:

        M [A/m] = (m × Z × μ_B) / V_cell,m³

    where ``Z`` is the number of formula units per unit cell and μ_B is the
    Bohr magneton. The saturation induction reported in tesla is:

        M_s [T] = μ₀ × M [A/m]

    Maximum energy product
    ----------------------
    For a fully aligned, single-phase, uniaxial hard magnet the Stoner–Wohlfarth
    upper bound on the maximum energy product is:

        (BH)_max [J/m³] = μ₀ M_s² / 4

    when ``M_s`` is expressed as magnetization in A/m. Equivalently, using
    ``B_r ≈ μ₀ M_s`` in tesla:

        (BH)_max [J/m³] = B_r² / (4 μ₀) ≈ M_s,T² / (4 μ₀)

    Convert to kJ/m³ and MGOe (1 MGOe = 7.958 kJ/m³).

    Parameters
    ----------
    magnetic_moment:
        Total magnetic moment in Bohr magnetons per formula unit (μB/f.u.).
    volume:
        Unit-cell volume in cubic ångströms (Å³).
    formula_units_per_cell:
        Number of formula units ``Z`` in the crystallographic unit cell.
        Defaults to 1 when unknown; set explicitly for accurate Ms (e.g. 8 for
        Nd₂Fe₁₄B in the Pnnm structure).

    Returns
    -------
    dict
        ``saturation_magnetization_tesla``, ``bhmax_kj_m3``, ``bhmax_mgoe``,
        and intermediate SI quantities for auditability.
    """
    if magnetic_moment < 0:
        raise ValueError("magnetic_moment must be non-negative.")
    if volume <= 0:
        raise ValueError("volume must be positive.")
    if formula_units_per_cell <= 0:
        raise ValueError("formula_units_per_cell must be a positive integer.")

    volume_m3 = volume * ANGSTROM3_TO_M3
    total_moment_mu_b = magnetic_moment * formula_units_per_cell

    # M [A/m] = (moment in μB) × μ_B [A·m²] / V [m³]
    magnetization_a_per_m = (total_moment_mu_b * MU_B) / volume_m3
    saturation_magnetization_tesla = MU0 * magnetization_a_per_m

    # Stoner–Wohlfarth upper bound: (BH)max = μ₀ M² / 4  [J/m³]
    bhmax_j_m3 = (MU0 * magnetization_a_per_m**2) / 4.0
    bhmax_kj_m3 = bhmax_j_m3 / 1000.0
    bhmax_mgoe = bhmax_kj_m3 / MGOE_TO_KJ_M3

    return {
        "magnetic_moment_mu_b_per_fu": round(magnetic_moment, 6),
        "unit_cell_volume_angstrom3": round(volume, 6),
        "formula_units_per_cell": formula_units_per_cell,
        "magnetization_a_per_m": round(magnetization_a_per_m, 4),
        "saturation_magnetization_tesla": round(saturation_magnetization_tesla, 6),
        "bhmax_j_m3": round(bhmax_j_m3, 4),
        "bhmax_kj_m3": round(bhmax_kj_m3, 4),
        "bhmax_mgoe": round(bhmax_mgoe, 4),
        "assumptions": {
            "moment_units": "μB per formula unit (Materials Project convention)",
            "volume_units": "Å³ (crystallographic unit cell)",
            "bhmax_model": "Stoner–Wohlfarth single-phase upper bound: (BH)max = μ₀Ms²/4",
            "note": (
                "Experimental (BH)max is typically 30–60% of this bound due to "
                "microstructure, anisotropy distribution, and coercivity limits."
            ),
        },
    }


def evaluate_permanent_magnet(
    formula: str,
    magnetic_moment: Optional[float] = None,
    volume: Optional[float] = None,
    formula_units_per_cell: int = 1,
) -> dict[str, Any]:
    """
    Run supply-chain criticality scoring and theoretical limit calculations.

    When ``magnetic_moment`` and/or ``volume`` are omitted, only the
    criticality analysis is returned; theoretical limits require both values.

    Parameters
    ----------
    formula:
        Chemical formula string.
    magnetic_moment:
        Optional μB/f.u. from Materials Project or experiment.
    volume:
        Optional unit-cell volume in Å³.
    formula_units_per_cell:
        Formula units per unit cell for Ms conversion (default 1).

    Returns
    -------
    dict
        Combined ``criticality`` and ``theoretical_limits`` payloads.
    """
    criticality = calculate_criticality_score(formula)

    result: dict[str, Any] = {
        "formula": formula.strip(),
        "criticality": criticality,
        "theoretical_limits": None,
    }

    if magnetic_moment is not None and volume is not None:
        result["theoretical_limits"] = calculate_theoretical_limits(
            magnetic_moment=magnetic_moment,
            volume=volume,
            formula_units_per_cell=formula_units_per_cell,
        )

    return result
