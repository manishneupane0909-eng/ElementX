from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


MaterialFamily = Literal["mnal_tau", "mnbi", "fe_soft", "other"]
SampleStatus = Literal["planned", "synthesized", "characterized"]
SynthesisMethod = Literal["arc_melt", "induction_melt", "ball_mill", "other"]
OutcomeLabel = Literal["success", "partial", "fail"]


class Dopant(BaseModel):
    element: str
    fraction: float = Field(ge=0, le=1)


class Synthesis(BaseModel):
    method: SynthesisMethod = "arc_melt"
    anneal_temp_c: Optional[float] = None
    anneal_time_h: Optional[float] = None
    notes: Optional[str] = None


class SampleCreate(BaseModel):
    name: str
    formula: str
    material_family: MaterialFamily = "mnal_tau"
    dopants: list[Dopant] = []
    synthesis: Synthesis = Synthesis()
    status: SampleStatus = "planned"
    project_name: Optional[str] = "RE-Free Magnets"
    stoichiometry: Optional[dict] = None


class SampleUpdate(BaseModel):
    name: Optional[str] = None
    formula: Optional[str] = None
    material_family: Optional[MaterialFamily] = None
    dopants: Optional[list[Dopant]] = None
    synthesis: Optional[Synthesis] = None
    status: Optional[SampleStatus] = None
    stoichiometry: Optional[dict] = None
    outcome_label: Optional[OutcomeLabel] = None


def sample_document(user_id: str, payload: SampleCreate) -> dict:
    now = datetime.utcnow()
    return {
        "userId": user_id,
        "projectName": payload.project_name,
        "name": payload.name,
        "formula": payload.formula,
        "materialFamily": payload.material_family,
        "dopants": [d.model_dump() for d in payload.dopants],
        "synthesis": payload.synthesis.model_dump(),
        "status": payload.status,
        "stoichiometry": payload.stoichiometry,
        "characterization": {"xrd": None, "magnetic": None},
        "phaseAnalysis": None,
        "outcomeLabel": None,
        "aiRecommendations": [],
        "createdAt": now,
        "updatedAt": now,
    }
