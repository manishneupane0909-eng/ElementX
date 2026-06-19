from typing import Any, Optional

from services.llm_client import chat_completion


async def generate_experiment_brief(
    sample: dict[str, Any],
    recommendations: list[dict[str, Any]],
    project_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    rec_text = "\n".join(
        f"- {r.get('suggestedFormula')} (confidence {r.get('confidence')}): {r.get('rationale')}"
        for r in recommendations
    ) or "No recommendations generated yet."

    phase = sample.get("phaseAnalysis") or {}
    mag = (sample.get("characterization") or {}).get("magnetic") or {}

    context = f"""
Sample: {sample.get('name')} ({sample.get('formula')})
Material family: {sample.get('materialFamily')}
Status: {sample.get('status')} | Outcome: {sample.get('outcomeLabel')}
Synthesis: {sample.get('synthesis')}
Dopants: {sample.get('dopants')}
Phase (τ-MnAl): {phase}
Magnetic summary: {mag.get('properties')}

Project sample count: {len(project_samples)}

AI recommendations:
{rec_text}
""".strip()

    system = (
        "You are a materials R&D assistant for rare-earth-free permanent magnet research. "
        "Write a concise Experiment Brief suitable for a PI, grant report, or industrial R&D log. "
        "Use markdown with sections: Executive Summary, Current Sample Status, Recommended Next Experiments "
        "(numbered), Risk Notes, Compliance/Record-Keeping note for US supply-chain documentation. "
        "Cite only facts from the provided context — do not invent peak positions or measured values."
    )
    user = f"Generate an experiment brief from this lab context:\n\n{context}"

    markdown, source = await chat_completion(system, user, max_tokens=2500, temperature=0.3)

    return {
        "markdown": markdown,
        "source": source,
        "sampleId": str(sample.get("_id", sample.get("id", ""))),
        "sampleName": sample.get("name"),
    }
