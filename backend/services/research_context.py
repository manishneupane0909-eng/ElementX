"""Build Physics Copilot context for research Samples from STORED analysis only.

Nothing here computes new science. Values are read back from the persisted
``analysis_json`` produced by the verified magnetometry / XRD pipelines and are
labelled with the vocabulary those pipelines use. In particular:

* the largest measured moment is reported as a measured maximum, never as a
  saturation magnetization;
* XRD maxima are "candidate intensity maxima" only - no phase, lattice or
  crystallite-size inference is made or implied.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

MAX_MH_SEGMENTS = 12
MAX_XRD_MAXIMA = 15


def _num(value: Any, digits: int = 4) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "not available"
    return f"{value:.{digits}g}"


def _get(mapping: Any, *path: str) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _mass_lines(first_analysis: Optional[dict], confirmed_mg: Optional[float]) -> list[str]:
    lines: list[str] = []
    provenance = _get(first_analysis, "mass_provenance")
    if isinstance(provenance, dict):
        lines.append(
            "  Mass provenance: status="
            f"{provenance.get('resolution_status')}, "
            f"resolved_mass_mg={_num(provenance.get('resolved_mass_mg'))}, "
            f"source={provenance.get('resolved_source')}, "
            f"normalization_allowed={provenance.get('normalization_allowed')}"
        )
    else:
        lines.append("  Mass provenance: not available")
    if confirmed_mg is not None:
        lines.append(f"  User-confirmed mass (mg): {_num(confirmed_mg)}")
    return lines


def _magnetometry_lines(experiment: Any) -> list[str]:
    analysis = experiment.analysis_json or {}
    summary = analysis.get("summary") or {}
    lines = [
        f"- Magnetometry experiment '{experiment.original_filename}' "
        f"(pipeline v{experiment.analysis_version}, uploaded {experiment.uploaded_at})",
        f"  M-H segments: {summary.get('mh_segment_count')}, "
        f"M-T segments: {summary.get('mt_segment_count')}, "
        f"normalization_available: {summary.get('normalization_available')}",
    ]
    entries = analysis.get("mh_analyses") or []
    first = entries[0].get("analysis") if entries and isinstance(entries[0], dict) else None
    lines.extend(_mass_lines(first, experiment.user_confirmed_mass_mg))

    for entry in entries[:MAX_MH_SEGMENTS]:
        item = entry.get("analysis") if isinstance(entry, dict) else None
        if not isinstance(item, dict):
            continue
        hysteresis = item.get("hysteresis") or {}
        high_field = item.get("high_field") or {}
        lines.append(
            f"  M-H segment {entry.get('segment_index')} "
            f"at mean T = {_num(hysteresis.get('mean_temperature_K'))} K: "
            f"Hc(-) = {_num(hysteresis.get('Hc_negative_Oe'))} Oe, "
            f"Hc(+) = {_num(hysteresis.get('Hc_positive_Oe'))} Oe, "
            f"Mr(-) = {_num(hysteresis.get('Mr_negative_emu'))} emu, "
            f"Mr(+) = {_num(hysteresis.get('Mr_positive_emu'))} emu; "
            f"high-field saturation evidence = {high_field.get('saturation_evidence_quality')}; "
            "largest measured |moment| = "
            f"{_num(high_field.get('maximum_absolute_measured_moment_emu'))} emu "
            "(a measured maximum, NOT a saturation magnetization)"
        )
        normalized = item.get("normalized") or {}
        if normalized.get("available"):
            mr_pos = _get(normalized, "Mr_positive", "specific_magnetization_emu_per_g")
            lines.append(
                f"    Mass-normalized Mr(+) = {_num(mr_pos)} emu/g "
                f"(mass source: {_get(normalized, 'Mr_positive', 'mass_source')})"
            )
        else:
            lines.append(
                "    Mass-normalized values: not available "
                f"(reason: {normalized.get('reason')})"
            )
        for warning in (hysteresis.get("warnings") or [])[:3]:
            lines.append(f"    Warning: {warning}")
    if len(entries) > MAX_MH_SEGMENTS:
        lines.append(f"  ({len(entries) - MAX_MH_SEGMENTS} further M-H segments omitted)")
    for warning in (analysis.get("warnings") or [])[:5]:
        lines.append(f"  File warning: {warning}")
    return lines


def _xrd_lines(experiment: Any) -> list[str]:
    analysis = experiment.analysis_json or {}
    summary = analysis.get("summary") or {}
    lines = [
        f"- XRD experiment '{experiment.original_filename}' "
        f"(pipeline v{experiment.analysis_version}, uploaded {experiment.uploaded_at})",
        f"  Measured pattern: {summary.get('point_count')} points, "
        f"2-theta {_num(summary.get('two_theta_min_deg'))} to "
        f"{_num(summary.get('two_theta_max_deg'))} deg, "
        f"intensity {_num(summary.get('intensity_min'))} to {_num(summary.get('intensity_max'))}",
    ]
    peaks = analysis.get("peaks") or []
    if peaks:
        formatted = ", ".join(
            f"{_num(p.get('two_theta_deg'))} deg (I={_num(p.get('intensity'))})"
            for p in peaks[:MAX_XRD_MAXIMA]
            if isinstance(p, dict)
        )
        lines.append(
            "  Candidate intensity maxima (local maxima only; NOT assigned to any phase, "
            f"hkl, lattice or crystallite size): {formatted}"
        )
    else:
        lines.append("  Candidate intensity maxima: none detected")
    for warning in (analysis.get("warnings") or [])[:5]:
        lines.append(f"  File warning: {warning}")
    return lines


def build_research_sample_context(sample: Any, experiments: Iterable[Any]) -> str:
    """Context for one owned research Sample, derived from stored analysis only."""
    experiments = list(experiments)
    lines = [
        "RESEARCH SAMPLE (stored records; values are read from saved analyses)",
        f"Name: {sample.name}",
        f"Formula: {sample.formula or 'not recorded'}",
        f"Notes: {sample.notes or 'none'}",
        f"Saved experiments: {len(experiments)}",
    ]
    if not experiments:
        lines.append("No experiments have been saved for this sample yet.")
    for experiment in experiments:
        if experiment.experiment_type == "magnetometry":
            lines.extend(_magnetometry_lines(experiment))
        elif experiment.experiment_type == "xrd":
            lines.extend(_xrd_lines(experiment))
        else:
            lines.append(
                f"- Experiment '{experiment.original_filename}' "
                f"(type {experiment.experiment_type}): no summary available"
            )
    return "\n".join(lines)


def build_research_overview_context(samples: Iterable[Any], counts: dict[str, int]) -> str:
    """Compact overview of the caller's research Samples (no per-experiment values)."""
    samples = list(samples)
    if not samples:
        return "The user has no saved research Samples yet."
    lines = ["RESEARCH SAMPLES (names only; select one for stored measurement values)"]
    for sample in samples[:50]:
        lines.append(
            f"- {sample.name} (formula: {sample.formula or 'not recorded'}), "
            f"{counts.get(sample.id, 0)} saved experiment(s)"
        )
    return "\n".join(lines)


RESEARCH_COPILOT_SYSTEM_PROMPT = (
    "You are the ElementX Physics Copilot for a permanent-magnet materials lab. "
    "Answer using ONLY the stored research records in the context below. "
    "Never invent or estimate measurements. "
    "Never describe the largest measured moment as saturation magnetization (Ms); "
    "only a measured maximum is available. "
    "XRD maxima are candidate intensity maxima only: do not assign phases, hkl indices, "
    "lattice parameters or crystallite sizes, and do not claim a phase is present or absent. "
    "If mass-normalized values are not available, say why instead of normalizing yourself. "
    "If something was not measured or is missing, say so and suggest what to measure. "
    "Keep answers concise."
)


def offline_research_answer(question: str, context: str) -> str:
    """Deterministic fallback when no LLM is configured: show the stored values."""
    return (
        "The language model is not configured, so this is a direct readout of your "
        "stored research records (no interpretation applied).\n\n"
        f"{context}"
    )
