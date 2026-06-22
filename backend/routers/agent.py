"""Chat route — runs calculators and ranker, then summarizes results."""

import json
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import database
import local_store
from auth import verify_token
from services.dopant_ranker import rank_dopant_recommendations
from services.experiment_brief import generate_experiment_brief
from services.llm_client import active_model, chat_completion, llm_available
from services.phase_detector import detect_tau_mnal
from services.physics_calculators import analyze_sample_physics
from services.sample_context import build_samples_context

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    sample_id: Optional[str] = None
    history: list[AgentMessage] = []


def _serialize(doc: dict) -> dict:
    if not database.DB_AVAILABLE:
        return local_store._serialize(doc)  # noqa: SLF001
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    for key in ("createdAt", "updatedAt"):
        if key in doc and doc[key] and hasattr(doc[key], "isoformat"):
            doc[key] = doc[key].isoformat()
    return doc


async def _full_sample(user_id: str, sample_id: str) -> Optional[dict]:
    if database.DB_AVAILABLE:
        if not ObjectId.is_valid(sample_id):
            return None
        sample = await database.db.samples.find_one(
            {"_id": ObjectId(sample_id), "userId": user_id}
        )
        if not sample:
            return None
        payload = _serialize(sample)
        payload["xrdRecords"] = [
            _serialize(d)
            async for d in database.db.xrd.find(
                {"userId": user_id, "sampleId": sample_id}
            ).sort("createdAt", -1)
        ]
        payload["magneticRecords"] = [
            _serialize(d)
            async for d in database.db.magnetic.find(
                {"userId": user_id, "sampleId": sample_id}
            ).sort("createdAt", -1)
        ]
        return payload

    return local_store.get_sample(sample_id, user_id)


async def _all_samples(user_id: str, project_name: Optional[str] = None) -> list[dict]:
    if database.DB_AVAILABLE:
        query: dict = {"userId": user_id}
        if project_name:
            query["projectName"] = project_name
        return [_serialize(d) async for d in database.db.samples.find(query).sort("createdAt", -1)]
    return [_serialize(d) for d in local_store.find_samples(user_id, project_name)]


def _detect_intents(message: str) -> set[str]:
    m = message.lower()
    intents: set[str] = set()
    if any(w in m for w in ["next", "recommend", "suggest", "what should", "try next", "improve"]):
        intents.add("recommend")
    if any(w in m for w in ["brief", "report", "summary", "write up", "document"]):
        intents.add("brief")
    if any(
        w in m
        for w in [
            "analyz", "analyse", "phase", "lattice", "crystallite", "size",
            "scherrer", "bragg", "bhmax", "energy product", "coerciv", "ms",
            "magnet", "hysteresis", "what did i get", "characteriz", "result",
            "good", "bad", "compare", "explain",
        ]
    ):
        intents.add("analyze")
    return intents


def _wants_visuals(message: str) -> bool:
    """Charts + metric cards only for full analysis / explicit plot requests."""
    m = message.lower()
    if any(
        p in m
        for p in [
            "plot",
            "graph",
            "chart",
            "visualiz",
            "show xrd",
            "show loop",
            "show pattern",
            "show the xrd",
            "show the m-h",
            "display",
        ]
    ):
        return True
    if any(
        p in m
        for p in [
            "analyze this sample",
            "analyze the",
            "full analysis",
            "characteriz",
            "what did i get",
            "tell me what i got",
            "everything about",
            "phase, lattice",
            "magnetic properties",
            "i just uploaded",
            "just uploaded",
        ]
    ):
        return True
    return False


@router.get("/status")
async def agent_status(_user=Depends(verify_token)):
    return {
        "llmAvailable": llm_available(),
        "model": active_model(),
        "tools": [
            "analyze_sample (phase, lattice, crystallite size, magnetics, BHmax)",
            "rank_experiments",
            "experiment_brief",
            "literature_grounding (roadmap)",
        ],
    }


@router.post("/chat")
async def agent_chat(payload: AgentChatRequest, user=Depends(verify_token)):
    user_id = user["userId"]
    intents = _detect_intents(payload.message)
    display_visuals = _wants_visuals(payload.message)

    sample = None
    if payload.sample_id:
        sample = await _full_sample(user_id, payload.sample_id)

    tools_used: list[str] = []
    analysis: Optional[dict] = None
    recommendations: Optional[list] = None
    rec_summary: Optional[str] = None
    brief: Optional[str] = None
    xrd_record = None
    mag_record = None

    # If a sample is in focus, always run the physics bundle (cheap + grounding).
    if sample:
        if not sample.get("phaseAnalysis"):
            xr = (sample.get("xrdRecords") or [{}])[0]
            if xr.get("peaks"):
                sample["phaseAnalysis"] = detect_tau_mnal(xr["peaks"])
        analysis = analyze_sample_physics(sample)
        tools_used.append("analyze_sample")
        if sample.get("xrdRecords"):
            xrd_record = sample["xrdRecords"][0]
        if sample.get("magneticRecords"):
            mag_record = sample["magneticRecords"][0]

    if "recommend" in intents:
        project_name = sample.get("projectName") if sample else None
        family = sample.get("materialFamily", "mnal_tau") if sample else "mnal_tau"
        project_docs = await _all_samples(user_id, project_name)
        ranked = rank_dopant_recommendations(
            project_docs, material_family=family, project_name=project_name, limit=3
        )
        recommendations = ranked["recommendations"]
        rec_summary = ranked["summary"]
        tools_used.append("rank_experiments")

    if "brief" in intents and sample:
        recs = recommendations or (sample.get("aiRecommendations") or [])
        project_docs = await _all_samples(user_id, sample.get("projectName"))
        brief_result = await generate_experiment_brief(sample, recs, project_docs)
        brief = brief_result.get("markdown")
        tools_used.append("experiment_brief")

    # Context passed to text generation — numbers come from calculators only.
    all_samples = await _all_samples(user_id)
    context_parts = [build_samples_context(all_samples, focus_sample_id=payload.sample_id)]
    if analysis:
        context_parts.append("PHYSICS ANALYSIS (computed, authoritative):\n" + json.dumps(analysis, indent=2))
    if recommendations:
        context_parts.append("RANKED EXPERIMENTS:\n" + json.dumps(recommendations, indent=2))
    context = "\n\n".join(context_parts)

    history_text = "\n".join(f"{m.role}: {m.content}" for m in payload.history[-6:])

    if llm_available():
        if display_visuals:
            system = (
                "You help with permanent magnet lab work (MnAl, MnBi, etc.). "
                "Use only the sample records and computed numbers below — do not invent peaks or magnetic values. "
                "Give a structured overview: phase, lattice, crystallite size, and magnetic properties when available. "
                "Cite the formula when you quote a number. If something was not measured, say what to run next."
            )
        else:
            system = (
                "You help with permanent magnet lab work (MnAl, MnBi, etc.). "
                "Answer ONLY what the user asked — do not dump the full characterization or repeat every metric. "
                "Use the computed numbers below as ground truth; never invent peaks or magnetic values. "
                "Keep replies short (1–3 sentences, or a short bullet list only if they asked for several things). "
                "If they ask about one property (e.g. coercivity, phase), state that value or say it was not measured. "
                "Add a brief explanation or one practical tip only when it directly helps their question "
                "(e.g. how to improve Hc, whether a value is typical). "
                "Do not use markdown headers or repeat data they already saw in earlier messages."
            )
        user_msg = (
            f"Conversation so far:\n{history_text}\n\n"
            f"Grounding context:\n{context}\n\n"
            f"User request: {payload.message}"
        )
        answer, source = await chat_completion(system, user_msg, max_tokens=1800)
    else:
        answer = _offline_answer(payload.message, analysis, recommendations, rec_summary, sample, display_visuals)
        source = "heuristic"

    return {
        "answer": answer,
        "source": source,
        "model": active_model(),
        "toolsUsed": tools_used,
        "displayVisuals": display_visuals,
        "analysis": analysis if display_visuals else None,
        "recommendations": recommendations,
        "recommendationSummary": rec_summary,
        "brief": brief,
        "xrdRecord": xrd_record if display_visuals else None,
        "magneticRecord": mag_record if display_visuals else None,
        "sampleId": payload.sample_id,
    }


def _offline_answer(message, analysis, recommendations, rec_summary, sample, display_visuals: bool) -> str:
    lines = ["(No API key in backend/.env — showing calculated results only.)\n"]
    if sample:
        lines.append(f"Sample: {sample.get('name')} ({sample.get('formula')})")

    m = message.lower()
    if analysis and not display_visuals:
        phase = analysis.get("phase") or {}
        mag = analysis.get("magnetics") or {}
        if any(w in m for w in ["phase", "tau", "mnal", "ε", "epsilon"]):
            if phase:
                lines.append(
                    f"Phase τ-MnAl: {'DETECTED' if phase.get('tauDetected') else 'not detected'}"
                    + (f" ({phase.get('matchedPeakCount')}/3 peaks)" if phase.get("tauDetected") else "")
                )
        elif any(w in m for w in ["coerciv", "hc"]):
            if mag.get("ok"):
                lines.append(f"Coercivity (Hc): {mag.get('Hc_Oe')} Oe")
            else:
                lines.append("Coercivity was not measured — run VSM and upload an M-H loop.")
        elif any(w in m for w in ["ms", "saturation", "remanence", "mr", "squareness", "bhmax", "energy product"]):
            if mag.get("ok"):
                lines.append(
                    f"Ms={mag.get('Ms_emu_g')} emu/g, Mr/Ms={mag.get('squareness_Mr_Ms')}, "
                    f"(BH)max≈{mag.get('bhmax_estimate_MGOe')} MGOe"
                )
            else:
                lines.append("Magnetic properties were not measured — upload VSM data.")
        elif any(w in m for w in ["lattice", "bragg", "d-spacing"]):
            lat = analysis.get("lattice") or {}
            if lat.get("ok"):
                lines.append(f"Lattice a (cubic est.): {lat.get('lattice_a_cubic')} Å — {lat.get('formula')}")
        elif any(w in m for w in ["crystallite", "scherrer", "grain"]):
            cs = analysis.get("crystallite") or {}
            if cs.get("ok"):
                lines.append(f"Crystallite size: {cs.get('crystallite_size_nm')} nm (Scherrer)")
        else:
            lines.append("Ask about a specific property (phase, Hc, Ms, lattice, etc.) or click Analyze sample for the full report.")
    elif analysis and display_visuals:
        phase = analysis.get("phase") or {}
        if phase:
            lines.append(
                f"Phase τ-MnAl: {'DETECTED' if phase.get('tauDetected') else 'not detected'}"
                + (f" ({phase.get('matchedPeakCount')}/3 peaks)" if phase.get("tauDetected") else "")
            )
        lat = analysis.get("lattice") or {}
        if lat.get("ok"):
            lines.append(f"Lattice a (cubic est.): {lat.get('lattice_a_cubic')} Å — {lat.get('formula')}")
        cs = analysis.get("crystallite") or {}
        if cs.get("ok"):
            lines.append(f"Crystallite size: {cs.get('crystallite_size_nm')} nm (Scherrer)")
        mag = analysis.get("magnetics") or {}
        if mag.get("ok"):
            lines.append(
                f"Magnetics: Ms={mag.get('Ms_emu_g')} emu/g, Hc={mag.get('Hc_Oe')} Oe, "
                f"squareness={mag.get('squareness_Mr_Ms')}, (BH)max≈{mag.get('bhmax_estimate_MGOe')} MGOe"
            )
    if recommendations:
        lines.append("\nNext experiments:")
        for i, r in enumerate(recommendations, 1):
            lines.append(f"  {i}. {r.get('suggestedFormula')} (conf {r.get('confidence')}) — {r.get('rationale')}")
    if rec_summary:
        lines.append(f"\n{rec_summary}")
    if len(lines) <= 1:
        lines.append("Select a sample, then ask for analysis, next alloy ideas, or a brief.")
    return "\n".join(lines)
