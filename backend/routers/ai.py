from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

import database
import local_store
from auth import verify_token
from services.llm_client import chat_completion, llm_available
from services.sample_context import build_samples_context, heuristic_copilot_answer
from services.synthesis_parser import parse_synthesis_notes

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ParseSynthesisRequest(BaseModel):
    notes: str = Field(min_length=1, max_length=10000)


class CopilotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    sample_id: str | None = None
    project_name: str | None = None


async def _load_user_samples(user_id: str, project_name: str | None = None) -> list[dict]:
    if database.DB_AVAILABLE:
        query: dict = {"userId": user_id}
        if project_name:
            query["projectName"] = project_name
        cursor = database.db.samples.find(query).sort("createdAt", -1)
        samples = []
        async for doc in cursor:
            doc = dict(doc)
            doc["id"] = str(doc.pop("_id"))
            samples.append(doc)
        return samples

    return [
        {**s, "id": str(s["_id"])}
        for s in local_store.find_samples(user_id, project_name)
    ]


@router.get("/status")
async def ai_status(_user=Depends(verify_token)):
    import os

    return {
        "llmAvailable": llm_available(),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "features": [
            "parse-synthesis",
            "copilot",
            "dopant-recommendations",
            "experiment-brief",
            "outcome-labels",
        ],
    }


@router.post("/parse-synthesis")
async def parse_synthesis(payload: ParseSynthesisRequest, user=Depends(verify_token)):
    result = await parse_synthesis_notes(payload.notes)
    return {"success": True, **result}


@router.post("/copilot")
async def copilot(payload: CopilotRequest, user=Depends(verify_token)):
    samples = await _load_user_samples(user["userId"], payload.project_name)
    context = build_samples_context(samples, focus_sample_id=payload.sample_id)

    if llm_available():
        system = (
            "You are Forge AI, a lab copilot for critical materials R&D (rare-earth-free magnets). "
            "Answer using ONLY the sample context below. Reference sample names/ids when relevant. "
            "If data is missing, say what measurement to run next. Never invent XRD peaks or magnetic values."
        )
        user_msg = f"Context:\n{context}\n\nQuestion: {payload.question}"
        answer, source = await chat_completion(system, user_msg, max_tokens=1500)
    else:
        answer = heuristic_copilot_answer(payload.question, context)
        source = "heuristic"

    return {
        "answer": answer,
        "source": source,
        "sampleCount": len(samples),
        "llmAvailable": llm_available(),
    }
