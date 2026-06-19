"""Bragg, Scherrer, and magnet summary helpers for linked sample data."""

import math
from typing import Any, Optional

# Cu Kα1 radiation (most common lab XRD source), in angstroms.
CU_KALPHA = 1.5406
SCHERRER_K = 0.9

# Default Miller indices used to label the strongest reflections (matches the
# frontend XRD plot convention). Cubic indexing approximation.
DEFAULT_HKL = [
    (1, 1, 1),
    (2, 0, 0),
    (2, 2, 0),
    (3, 1, 1),
    (2, 2, 2),
    (4, 0, 0),
]


def d_spacing(two_theta_deg: float, wavelength: float = CU_KALPHA) -> float:
    """Bragg's law: d = λ / (2 sinθ).  two_theta is in degrees."""
    theta = math.radians(two_theta_deg / 2.0)
    s = math.sin(theta)
    if s <= 0:
        return float("nan")
    return wavelength / (2.0 * s)


def bragg_lattice(peaks: list[dict], wavelength: float = CU_KALPHA) -> dict[str, Any]:
    """Estimate d-spacings for each peak and a cubic lattice parameter.

    Assigns Miller indices to the strongest peaks (ordered by angle), then
    estimates a = d * sqrt(h^2 + k^2 + l^2) per peak and averages.
    NOTE: cubic approximation; tetragonal phases (e.g. L1_0 τ-MnAl) need full
    indexing for exact a, c — flagged in the assumptions field.
    """
    if not peaks:
        return {"ok": False, "reason": "no peaks"}

    by_intensity = sorted(peaks, key=lambda p: p.get("intensity", 0), reverse=True)
    top = by_intensity[: len(DEFAULT_HKL)]
    top.sort(key=lambda p: p["angle"])

    rows = []
    a_estimates = []
    for (h, k, l), peak in zip(DEFAULT_HKL, top):
        d = d_spacing(peak["angle"], wavelength)
        m = math.sqrt(h * h + k * k + l * l)
        a = d * m
        a_estimates.append(a)
        rows.append(
            {
                "two_theta": round(peak["angle"], 3),
                "hkl": f"({h}{k}{l})",
                "d_spacing": round(d, 4),
                "a_from_peak": round(a, 4),
            }
        )

    a_mean = sum(a_estimates) / len(a_estimates) if a_estimates else float("nan")
    return {
        "ok": True,
        "wavelength": wavelength,
        "rows": rows,
        "lattice_a_cubic": round(a_mean, 4),
        "formula": "d = λ / (2·sinθ);  a = d·√(h²+k²+l²)",
        "assumptions": "Cu Kα1 (1.5406 Å); cubic indexing approximation.",
    }


def _fwhm_degrees(data: list[dict], peak_angle: float, window: float = 2.0) -> Optional[float]:
    """Estimate FWHM (in 2θ degrees) of a peak from raw (angle,intensity) data."""
    pts = [
        (p["angle"], p["intensity"])
        for p in data
        if abs(p["angle"] - peak_angle) <= window
    ]
    if len(pts) < 5:
        return None
    pts.sort(key=lambda x: x[0])
    angles = [a for a, _ in pts]
    intens = [i for _, i in pts]

    baseline = min(intens)
    peak_val = max(intens)
    half = baseline + (peak_val - baseline) / 2.0
    peak_idx = intens.index(peak_val)

    # Walk left and right to the half-max crossings.
    left = None
    for j in range(peak_idx, 0, -1):
        if intens[j] <= half:
            left = angles[j]
            break
    right = None
    for j in range(peak_idx, len(intens)):
        if intens[j] <= half:
            right = angles[j]
            break
    if left is None or right is None or right <= left:
        return None
    return right - left


def scherrer_size(
    data: list[dict],
    peaks: list[dict],
    wavelength: float = CU_KALPHA,
    k: float = SCHERRER_K,
) -> dict[str, Any]:
    """Crystallite size from the strongest peak: t = Kλ / (β·cosθ)."""
    if not peaks or not data:
        return {"ok": False, "reason": "need peaks and raw data"}

    strongest = max(peaks, key=lambda p: p.get("intensity", 0))
    fwhm_deg = _fwhm_degrees(data, strongest["angle"])
    if not fwhm_deg:
        return {"ok": False, "reason": "could not measure FWHM"}

    beta = math.radians(fwhm_deg)
    theta = math.radians(strongest["angle"] / 2.0)
    cos_t = math.cos(theta)
    if beta <= 0 or cos_t <= 0:
        return {"ok": False, "reason": "invalid geometry"}

    t_angstrom = (k * wavelength) / (beta * cos_t)
    t_nm = t_angstrom / 10.0
    return {
        "ok": True,
        "peak_two_theta": round(strongest["angle"], 3),
        "fwhm_deg": round(fwhm_deg, 4),
        "crystallite_size_nm": round(t_nm, 1),
        "formula": "t = K·λ / (β·cosθ),  K=0.9",
        "assumptions": "Instrumental broadening not subtracted; size is a lower-bound estimate.",
    }


def magnetic_summary(
    data: list[dict],
    properties: dict,
    density_g_cm3: float = 5.1,
) -> dict[str, Any]:
    """Loop metrics + a (BH)max estimate from the second quadrant.

    Inputs: data points {x: field(Oe), y: moment(emu/g)}, properties {Ms,Mr,Hc}.
    True (BH)max requires density to convert emu/g → volumetric magnetization,
    so we report it as an estimate with the assumed density stated.
    """
    ms = properties.get("Ms")
    mr = properties.get("Mr")
    hc = properties.get("Hc")
    squareness = round(mr / ms, 3) if (ms and mr and ms > 0) else None

    bhmax_proxy = None
    bhmax_mgoe = None
    if data:
        # Second quadrant: H < 0, M > 0.
        second_q = [(p["x"], p["y"]) for p in data if p["x"] < 0 and p["y"] > 0]
        if second_q:
            # Relative energy-product proxy in (Oe·emu/g).
            bhmax_proxy = max(abs(h * m) for h, m in second_q)
            # Approximate (BH)max in MGOe using assumed density.
            # M(emu/g)*ρ(g/cm³) = M(emu/cm³); 4πM gives induction contribution (G).
            # (BH)max[MGOe] ≈ max(|H[Oe] * 4π*M_vol[G]|)/1e6 over 2nd quadrant.
            best = 0.0
            for h, m in second_q:
                m_vol = m * density_g_cm3  # emu/cm^3
                b_contrib = 4 * math.pi * m_vol  # Gauss
                best = max(best, abs(h * b_contrib))
            bhmax_mgoe = round(best / 1e6, 2)

    return {
        "ok": True,
        "Ms_emu_g": round(ms, 2) if ms is not None else None,
        "Mr_emu_g": round(mr, 2) if mr is not None else None,
        "Hc_Oe": round(hc, 1) if hc is not None else None,
        "squareness_Mr_Ms": squareness,
        "bhmax_estimate_MGOe": bhmax_mgoe,
        "bhmax_proxy_Oe_emu_g": round(bhmax_proxy, 1) if bhmax_proxy else None,
        "assumptions": f"(BH)max assumes density ρ={density_g_cm3} g/cm³; emu/g→volumetric conversion approximate.",
    }


def analyze_sample_physics(sample: dict) -> dict[str, Any]:
    """Run the full deterministic physics bundle on a stored sample."""
    result: dict[str, Any] = {"sampleId": sample.get("id"), "name": sample.get("name")}

    xrd_records = sample.get("xrdRecords") or []
    mag_records = sample.get("magneticRecords") or []

    if xrd_records and xrd_records[0].get("peaks"):
        peaks = xrd_records[0]["peaks"]
        data = xrd_records[0].get("data") or []
        result["phase"] = sample.get("phaseAnalysis")
        result["lattice"] = bragg_lattice(peaks)
        result["crystallite"] = scherrer_size(data, peaks)
    else:
        result["xrd_missing"] = True

    if mag_records and mag_records[0].get("properties"):
        result["magnetics"] = magnetic_summary(
            mag_records[0].get("data") or [],
            mag_records[0]["properties"],
        )
    else:
        result["magnetics_missing"] = True

    return result
