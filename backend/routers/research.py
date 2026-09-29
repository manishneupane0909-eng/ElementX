"""Scientific sample / experiment persistence (SQLite). Distinct from v2 /api/samples."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.db import get_db
from services.experiment_records import (
    ExperimentNotFoundError,
    InvalidMagnetometryUploadError,
    InvalidSampleError,
    SampleNotFoundError,
    create_magnetometry_experiment,
    create_sample,
    create_xrd_experiment,
    get_experiment,
    get_sample,
    list_experiment_summaries,
    list_samples,
    sample_experiment_counts,
)
from services.hysteresis import HysteresisAnalysisError
from services.magnetometry import MagnetometrySegmentationError
from services.mh_analysis import MHAnalysisError
from services.parsers.quantum_design import QuantumDesignParseError
from services.sample_provenance import SampleProvenanceError
from services.saturation import SaturationAnalysisError
from services.xrd_analysis import ALLOWED_XRD_SUFFIXES, InvalidXrdUploadError

router = APIRouter(prefix="/api/research", tags=["research"])


class ScientificSampleCreate(BaseModel):
    name: str
    formula: Optional[str] = None
    notes: Optional[str] = None


def _sample_payload(sample: Any, experiment_count: Optional[int] = None) -> dict:
    payload = {
        "id": sample.id,
        "name": sample.name,
        "formula": sample.formula,
        "notes": sample.notes,
        "created_at": sample.created_at,
        "updated_at": sample.updated_at,
    }
    if experiment_count is not None:
        payload["experiment_count"] = experiment_count
    return payload


def _experiment_summary_payload(row: Any) -> dict:
    return {
        "id": row.id,
        "experiment_type": row.experiment_type,
        "original_filename": row.original_filename,
        "uploaded_at": row.uploaded_at,
        "analysis_version": row.analysis_version,
    }


def _experiment_detail_payload(experiment: Any) -> dict:
    return {
        "id": experiment.id,
        "sample_id": experiment.sample_id,
        "experiment_type": experiment.experiment_type,
        "original_filename": experiment.original_filename,
        "uploaded_at": experiment.uploaded_at,
        "analysis_version": experiment.analysis_version,
        "user_confirmed_mass_mg": experiment.user_confirmed_mass_mg,
        "analysis_json": experiment.analysis_json,
    }


@router.post("/samples", status_code=201)
def create_scientific_sample(body: ScientificSampleCreate, db: Session = Depends(get_db)):
    try:
        sample = create_sample(db, body.name, body.formula, body.notes)
    except InvalidSampleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _sample_payload(sample, experiment_count=0)


@router.get("/samples")
def list_scientific_samples(db: Session = Depends(get_db)):
    samples = list_samples(db)
    counts = sample_experiment_counts(db, [sample.id for sample in samples])
    return [
        _sample_payload(sample, experiment_count=counts.get(sample.id, 0))
        for sample in samples
    ]


@router.get("/samples/{sample_id}")
def get_scientific_sample(sample_id: str, db: Session = Depends(get_db)):
    try:
        sample = get_sample(db, sample_id)
        summaries = list_experiment_summaries(db, sample_id)
    except SampleNotFoundError:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return {
        **_sample_payload(sample, experiment_count=len(summaries)),
        "experiments": [_experiment_summary_payload(row) for row in summaries],
    }


@router.post("/samples/{sample_id}/experiments", status_code=201)
async def create_scientific_experiment(
    sample_id: str,
    file: UploadFile = File(...),
    user_confirmed_mass_mg: Optional[float] = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A .dat filename is required.")

    if not file.filename.lower().endswith(".dat"):
        raise HTTPException(status_code=400, detail="Only .dat files are supported.")

    try:
        content = await file.read()
        experiment = create_magnetometry_experiment(
            db,
            sample_id=sample_id,
            original_filename=file.filename,
            content=content,
            user_confirmed_mass_mg=user_confirmed_mass_mg,
        )
        return _experiment_detail_payload(experiment)
    except HTTPException:
        raise
    except SampleNotFoundError:
        raise HTTPException(status_code=404, detail="Sample not found.")
    except InvalidMagnetometryUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QuantumDesignParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MagnetometrySegmentationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HysteresisAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SaturationAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SampleProvenanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MHAnalysisError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to save experiment.",
        )


@router.post("/samples/{sample_id}/xrd-experiments", status_code=201)
async def create_scientific_xrd_experiment(
    sample_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="An XRD filename is required.")

    suffix = file.filename.lower()
    if not any(suffix.endswith(allowed) for allowed in ALLOWED_XRD_SUFFIXES):
        raise HTTPException(
            status_code=400,
            detail="Only .txt, .csv, .xy, and two-column .dat XRD files are supported.",
        )

    try:
        content = await file.read()
        experiment = create_xrd_experiment(
            db,
            sample_id=sample_id,
            original_filename=file.filename,
            content=content,
        )
        return _experiment_detail_payload(experiment)
    except HTTPException:
        raise
    except SampleNotFoundError:
        raise HTTPException(status_code=404, detail="Sample not found.")
    except InvalidXrdUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to save XRD experiment.",
        )


@router.get("/experiments/{experiment_id}")
def get_scientific_experiment(experiment_id: str, db: Session = Depends(get_db)):
    try:
        experiment = get_experiment(db, experiment_id)
    except ExperimentNotFoundError:
        raise HTTPException(status_code=404, detail="Experiment not found.")
    return _experiment_detail_payload(experiment)
