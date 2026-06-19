from typing import Any, Optional


def _compact_sample(sample: dict) -> dict[str, Any]:
    char = sample.get("characterization") or {}
    xrd = char.get("xrd") or {}
    mag = char.get("magnetic") or {}
    phase = sample.get("phaseAnalysis")

    return {
        "id": sample.get("id") or str(sample.get("_id", "")),
        "name": sample.get("name"),
        "formula": sample.get("formula"),
        "materialFamily": sample.get("materialFamily"),
        "status": sample.get("status"),
        "outcomeLabel": sample.get("outcomeLabel"),
        "dopants": sample.get("dopants") or [],
        "synthesis": sample.get("synthesis"),
        "phaseAnalysis": phase,
        "xrdPeakCount": len(xrd.get("peaks") or []),
        "tauDetected": bool(phase and phase.get("tauDetected")),
        "magneticProperties": (mag.get("properties") if mag else None),
    }


def build_samples_context(samples: list[dict], *, focus_sample_id: Optional[str] = None) -> str:
    lines = [f"Total samples: {len(samples)}\n"]
    if focus_sample_id:
        focus = next(
            (s for s in samples if (s.get("id") or str(s.get("_id", ""))) == focus_sample_id),
            None,
        )
        if focus:
            lines.append("FOCUS SAMPLE:\n" + _format_sample_block(_compact_sample(focus)) + "\n")

    lines.append("ALL SAMPLES (newest first):")
    for sample in samples[:40]:
        compact = _compact_sample(sample)
        lines.append(_format_sample_block(compact))
    return "\n".join(lines)


def _format_sample_block(s: dict[str, Any]) -> str:
    parts = [
        f"- [{s.get('id', '?')[:8]}] {s.get('name')} | {s.get('formula')} | "
        f"family={s.get('materialFamily')} | status={s.get('status')} | outcome={s.get('outcomeLabel')}"
    ]
    if s.get("dopants"):
        dop = ", ".join(f"{d.get('element')} {d.get('fraction')}" for d in s["dopants"])
        parts.append(f"  dopants: {dop}")
    syn = s.get("synthesis") or {}
    if syn:
        parts.append(
            f"  synthesis: {syn.get('method')} "
            f"anneal={syn.get('anneal_temp_c')}C/{syn.get('anneal_time_h')}h "
            f"notes={syn.get('notes') or ''}"
        )
    if s.get("tauDetected"):
        parts.append("  phase: τ-MnAl DETECTED")
    elif s.get("xrdPeakCount"):
        parts.append(f"  phase: XRD uploaded ({s.get('xrdPeakCount')} peaks), τ not flagged")
    mag = s.get("magneticProperties")
    if mag:
        parts.append(
            f"  magnetic: Ms={mag.get('Ms')} Mr={mag.get('Mr')} Hc={mag.get('Hc')}"
        )
    return "\n".join(parts)


def heuristic_copilot_answer(question: str, context: str) -> str:
    q = question.lower()
    lines = []

    if "tau" in q or "phase" in q:
        tau_hits = [ln for ln in context.splitlines() if "τ-MnAl DETECTED" in ln]
        if tau_hits:
            lines.append("Samples with τ-phase detected:")
            lines.extend(tau_hits[:5])
        else:
            lines.append("No τ-MnAl detections in linked sample context yet.")

    if "fail" in q or "success" in q or "outcome" in q:
        outcome_lines = [ln for ln in context.splitlines() if "outcome=" in ln and "outcome=None" not in ln]
        if outcome_lines:
            lines.append("Labeled outcomes:")
            lines.extend(outcome_lines[:8])
        else:
            lines.append("No outcome labels yet — mark samples success/partial/fail to train the ranker.")

    if "dopant" in q or "next" in q or "recommend" in q:
        lines.append("Use POST /api/samples/{id}/recommend for ranked dopant suggestions.")

    if not lines:
        lines.append("Sample context loaded. Ask about τ-phase, dopants, outcomes, or magnetic properties.")
        lines.append("")
        lines.append(context[:3500])

    return "\n".join(lines)
