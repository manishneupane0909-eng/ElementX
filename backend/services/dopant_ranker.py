from datetime import datetime
from typing import Any, Optional

MODEL_VERSION = "ranker-v0-heuristic"

CANDIDATE_DOPANTS: dict[str, list[str]] = {
    "mnal_tau": ["C", "B", "Ga", "In", "Si", "Cu", "Zn"],
    "mnbi": ["C", "Fe", "Sn", "Cu"],
    "fe_soft": ["Si", "Al", "Mo", "Cr"],
    "other": ["C", "B", "Si"],
}

BASE_FORMULAS: dict[str, str] = {
    "mnal_tau": "MnAl",
    "mnbi": "MnBi",
    "fe_soft": "Fe",
    "other": "MnAl",
}


def _sample_success_score(sample: dict) -> float:
    outcome = sample.get("outcomeLabel")
    if outcome == "success":
        return 1.0
    if outcome == "partial":
        return 0.55
    if outcome == "fail":
        return 0.0

    phase = sample.get("phaseAnalysis") or {}
    if phase.get("tauDetected"):
        return 0.85

    mag = (sample.get("characterization") or {}).get("magnetic") or {}
    props = mag.get("properties") or {}
    ms = props.get("Ms")
    if ms and ms > 0:
        return min(0.75, 0.35 + ms / 500.0)

    if sample.get("status") == "characterized":
        return 0.25
    return 0.1


def _dopant_stats(samples: list[dict]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for sample in samples:
        score = _sample_success_score(sample)
        for dopant in sample.get("dopants") or []:
            el = dopant.get("element")
            if not el:
                continue
            bucket = stats.setdefault(el, {"attempts": 0, "weighted_success": 0.0})
            bucket["attempts"] += 1
            bucket["weighted_success"] += score
    return stats


def _format_formula(base: str, dopant: str, fraction: float) -> str:
    pct = fraction * 100
    if dopant == "C":
        return f"{base}{dopant}{fraction:.3f}".replace("0.000", "")
    return f"{base} + {dopant} ({pct:.1f}%)"


def rank_dopant_recommendations(
    samples: list[dict],
    *,
    material_family: str = "mnal_tau",
    project_name: Optional[str] = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    family = material_family if material_family in CANDIDATE_DOPANTS else "other"
    candidates = CANDIDATE_DOPANTS[family]
    base = BASE_FORMULAS.get(family, "MnAl")
    stats = _dopant_stats(samples)

    tried_dopants = set(stats.keys())
    ranked: list[dict[str, Any]] = []

    for dopant in candidates:
        fraction = 0.05 if dopant == "C" else 0.02
        s = stats.get(dopant, {"attempts": 0, "weighted_success": 0.0})
        attempts = int(s["attempts"])
        avg_success = (s["weighted_success"] / attempts) if attempts else None

        if attempts == 0:
            score = 0.92
            rationale = (
                f"{dopant} has not been tried in this project — high information gain for "
                f"{family} stabilization."
            )
        elif avg_success is not None and avg_success >= 0.6:
            score = 0.75 + min(0.2, avg_success * 0.2)
            rationale = (
                f"Prior runs with {dopant} scored well (avg success {avg_success:.2f}); "
                "consider adjacent stoichiometry."
            )
        elif avg_success is not None and avg_success < 0.35:
            score = 0.15
            rationale = f"{dopant} underperformed in prior attempts — deprioritized unless exploring failures."
        else:
            score = 0.45
            rationale = f"{dopant} has mixed results — worth a controlled repeat with tighter anneal window."

        if dopant in tried_dopants and attempts >= 3 and (avg_success or 0) < 0.4:
            continue

        ranked.append(
            {
                "suggestedFormula": _format_formula(base, dopant, fraction),
                "dopant": {"element": dopant, "fraction": fraction},
                "confidence": round(min(0.99, max(0.1, score)), 2),
                "rationale": rationale,
                "priorityScore": score,
            }
        )

    ranked.sort(key=lambda x: x["priorityScore"], reverse=True)
    top = ranked[:limit]

    project_ctx = f" project '{project_name}'" if project_name else ""
    characterized = sum(1 for s in samples if s.get("status") == "characterized")
    summary = (
        f"Ranked {len(top)} candidates from {len(samples)} samples in{project_ctx} "
        f"({characterized} characterized). Model: {MODEL_VERSION}."
    )

    now = datetime.utcnow().isoformat() + "Z"
    for item in top:
        item["generatedAt"] = now
        item["modelVersion"] = MODEL_VERSION
        del item["priorityScore"]

    return {"recommendations": top, "summary": summary, "modelVersion": MODEL_VERSION}
