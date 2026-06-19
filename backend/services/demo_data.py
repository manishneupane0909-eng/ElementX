"""Synthetic XRD/VSM curves for the demo account."""

import numpy as np


def synthetic_xrd_pattern(
    peak_angles: list[float],
    *,
    angle_min: float = 25.0,
    angle_max: float = 65.0,
    n_points: int = 400,
    noise: float = 0.015,
) -> list[tuple[float, float]]:
    angles = np.linspace(angle_min, angle_max, n_points)
    baseline = 80 + 20 * np.sin(angles / 8)
    intensity = baseline.copy()
    for peak in peak_angles:
        intensity += 1200 * np.exp(-0.5 * ((angles - peak) / 0.25) ** 2)
    rng = np.random.default_rng(42)
    intensity += rng.normal(0, noise * intensity.max(), size=n_points)
    intensity = np.clip(intensity, 0, None)
    return [(float(a), float(i)) for a, i in zip(angles, intensity)]


def synthetic_mh_loop(
    *,
    ms: float = 85.0,
    hc: float = 1200.0,
    field_max: float = 30000.0,
    n_points: int = 240,
) -> list[tuple[float, float]]:
    """Two-branch hysteresis loop: descending then ascending field sweep."""
    half = n_points // 2
    knee = max(field_max / 8.0, hc * 3)

    down = np.linspace(field_max, -field_max, half)
    up = np.linspace(-field_max, field_max, half)

    m_down = ms * np.tanh((down + hc) / knee)
    m_up = ms * np.tanh((up - hc) / knee)

    pts = [(float(h), float(m)) for h, m in zip(down, m_down)]
    pts += [(float(h), float(m)) for h, m in zip(up, m_up)]
    return pts


def pattern_to_text(points: list[tuple[float, float]]) -> str:
    lines = ["# ElementX demo XRD — angle (2θ) vs intensity"]
    for angle, intensity in points:
        lines.append(f"{angle:.4f}\t{intensity:.2f}")
    return "\n".join(lines) + "\n"


def mh_to_text(points: list[tuple[float, float]]) -> str:
    lines = ["# ElementX demo VSM — field (Oe) vs moment (emu/g)"]
    for x, y in points:
        lines.append(f"{x:.2f}\t{y:.4f}")
    return "\n".join(lines) + "\n"


# τ-MnAl reference peaks (matches phase_detector.py)
TAU_PEAKS = [35.5, 42.1, 58.3]

DEMO_SAMPLES = [
    {
        "name": "DEMO MnAl-C 5%",
        "formula": "Mn1.05Al0.95C0.05",
        "material_family": "mnal_tau",
        "dopants": [{"element": "C", "fraction": 0.05}],
        "synthesis": {
            "method": "arc_melt",
            "anneal_temp_c": 450,
            "anneal_time_h": 2,
            "notes": "Arc melted under Ar, annealed 450°C / 2h — τ-phase target",
        },
        "status": "characterized",
        "outcome_label": "success",
        "xrd_peaks": TAU_PEAKS,
        "magnetic_ms": 92.0,
    },
    {
        "name": "DEMO MnAl baseline",
        "formula": "MnAl",
        "material_family": "mnal_tau",
        "dopants": [],
        "synthesis": {
            "method": "arc_melt",
            "anneal_temp_c": 400,
            "anneal_time_h": 1,
            "notes": "Undoped baseline — ε-phase dominant",
        },
        "status": "characterized",
        "outcome_label": "fail",
        "xrd_peaks": [38.2, 44.8, 52.1],
        "magnetic_ms": 28.0,
    },
    {
        "name": "DEMO MnAl-B 2%",
        "formula": "MnAl + B (2%)",
        "material_family": "mnal_tau",
        "dopants": [{"element": "B", "fraction": 0.02}],
        "synthesis": {
            "method": "induction_melt",
            "anneal_temp_c": 480,
            "anneal_time_h": 3,
            "notes": "B stabilizer trial — partial τ conversion",
        },
        "status": "characterized",
        "outcome_label": "partial",
        "xrd_peaks": [35.5, 42.0],
        "magnetic_ms": 58.0,
    },
]

DEMO_PROJECT = "DEMO — RE-Free Magnets"

DEMO_EMAIL = "demo@elementx.dev"
DEMO_PASSWORD = "demo2026"
DEMO_NAME = "Demo User"
