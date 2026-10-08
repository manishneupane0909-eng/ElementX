"""Physics Copilot chat grounded in the caller's saved research Samples.

This is an additive route. The existing ``/api/agent/*`` and ``/api/ai/*`` routes are
unchanged. Context is built only from stored analysis values owned by the
authenticated user (see ``services.research_context``); no legacy physics
calculators are run, so no ``Ms = max|M|`` or phase inference can enter a reply.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import current_owner_id, verify_token
from services.db import get_db
from services.experiment_records import (
    SampleNotFoundError,
    get_sample,
    list_owner_experiments,
    list_samples,
    sample_experiment_counts,
)
from services.llm_client import active_model, chat_completion, llm_available
from services.research_context import (
    RESEARCH_COPILOT_SYSTEM_PROMPT,
    build_research_overview_context,
    build_research_sample_context,
    offline_research_answer,
)

logger = logging.getLogger("elementx")

router = APIRouter(
    prefix="/api/research-copilot",
    tags=["research-copilot"],
    dependencies=[Depends(verify_token)],
)


class ResearchChatMessage(BaseModel):
    role: str
    content: str = Field(max_length=6000)


class ResearchChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    sample_id: Optional[str] = None
    history: list[ResearchChatMessage] = []


@router.get("/status")
async def research_copilot_status():
    return {
        "llmAvailable": llm_available(),
        "model": active_model(),
        "researchContext": True,
    }


@router.post("/chat")
async def research_copilot_chat(
    payload: ResearchChatRequest,
    owner_id: str = Depends(current_owner_id),
    db: Session = Depends(get_db),
):
    sample_name: Optional[str] = None
    if payload.sample_id:
        try:
            sample = get_sample(db, payload.sample_id, owner_id)
        except SampleNotFoundError:
            raise HTTPException(status_code=404, detail="Sample not found.")
        experiments = list_owner_experiments(db, payload.sample_id, owner_id)
        context = build_research_sample_context(sample, experiments)
        sample_name = sample.name
    else:
        samples = list_samples(db, owner_id)
        counts = sample_experiment_counts(db, [s.id for s in samples])
        context = build_research_overview_context(samples, counts)

    history_text = "\n".join(
        f"{'assistant' if m.role == 'assistant' else 'user'}: {m.content}"
        for m in payload.history[-6:]
    )

    answer: Optional[str] = None
    source = "stored-records"
    if llm_available():
        user_message = (
            f"Conversation so far:\n{history_text}\n\n"
            f"Stored research records:\n{context}\n\n"
            f"User question: {payload.message}"
        )
        text, llm_source = await chat_completion(
            RESEARCH_COPILOT_SYSTEM_PROMPT, user_message, max_tokens=1500
        )
        if llm_source != "heuristic" and text.strip():
            answer, source = text, llm_source

    if answer is None:
        answer = offline_research_answer(payload.message, context)

    return {
        "answer": answer,
        "source": source,
        "model": active_model(),
        "sampleId": payload.sample_id,
        "sampleName": sample_name,
        "researchContext": True,
        "llmAvailable": llm_available(),
    }
