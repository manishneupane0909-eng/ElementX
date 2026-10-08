"""Persist scientific uploads as Sample experiments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from models.research import Experiment, Sample
from services.magnetometry_analysis import (
    MAGNETOMETRY_PIPELINE_VERSION,
    analyze_quantum_design_magnetometry,
)
from services.parsers.quantum_design import is_quantum_design_dat
from services.storage import remove_experiment_directory, write_original_dat, write_original_file
from services.xrd_analysis import (
    XRD_PIPELINE_VERSION,
    analyze_xrd_bytes,
    suffix_for_xrd_filename,
)

EXPERIMENT_TYPE_MAGNETOMETRY = "magnetometry"
EXPERIMENT_TYPE_XRD = "xrd"


class SampleNotFoundError(LookupError):
    """Raised when a sample id does not exist."""


class ExperimentNotFoundError(LookupError):
    """Raised when an experiment id does not exist."""


class InvalidSampleError(ValueError):
    """Raised when sample fields are invalid."""


class InvalidMagnetometryUploadError(ValueError):
    """Raised when an upload is not a Quantum Design .dat file."""


def _require_owner(owner_user_id: Optional[str]) -> str:
    if not isinstance(owner_user_id, str) or not owner_user_id.strip():
        raise ValueError("An authenticated owner is required.")
    return owner_user_id


def create_sample(
    db: Session,
    name: str,
    formula: Optional[str] = None,
    notes: Optional[str] = None,
    *,
    owner_user_id: str,
) -> Sample:
    owner_user_id = _require_owner(owner_user_id)
    stripped_name = name.strip()
    if not stripped_name:
        raise InvalidSampleError("Sample name is required.")
    now = datetime.now(timezone.utc)
    sample = Sample(
        id=str(uuid4()),
        name=stripped_name,
        formula=_optional_text(formula),
        notes=_optional_text(notes),
        owner_user_id=owner_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


def list_samples(db: Session, owner_user_id: str) -> list[Sample]:
    owner_user_id = _require_owner(owner_user_id)
    return list(
        db.scalars(
            select(Sample)
            .where(Sample.owner_user_id == owner_user_id)
            .order_by(Sample.created_at.desc())
        ).all()
    )


def sample_experiment_counts(db: Session, sample_ids: list[str]) -> dict[str, int]:
    if not sample_ids:
        return {}
    rows = db.execute(
        select(Experiment.sample_id, func.count())
        .where(Experiment.sample_id.in_(sample_ids))
        .group_by(Experiment.sample_id)
    ).all()
    return {sample_id: count for sample_id, count in rows}


def get_sample(db: Session, sample_id: str, owner_user_id: str) -> Sample:
    """Return a sample owned by ``owner_user_id``.

    A sample that exists but belongs to someone else (or to nobody) is reported
    exactly like a missing sample so ids cannot be probed across accounts.
    """
    owner_user_id = _require_owner(owner_user_id)
    sample = db.get(Sample, sample_id)
    if sample is None or sample.owner_user_id != owner_user_id:
        raise SampleNotFoundError(sample_id)
    return sample


def list_experiment_summaries(db: Session, sample_id: str, owner_user_id: str) -> list[tuple]:
    get_sample(db, sample_id, owner_user_id)
    return list(
        db.execute(
            select(
                Experiment.id,
                Experiment.experiment_type,
                Experiment.original_filename,
                Experiment.uploaded_at,
                Experiment.analysis_version,
            )
            .where(Experiment.sample_id == sample_id)
            .order_by(Experiment.uploaded_at.desc())
        ).all()
    )


def get_experiment(db: Session, experiment_id: str, owner_user_id: str) -> Experiment:
    """Return an experiment whose parent sample is owned by ``owner_user_id``."""
    owner_user_id = _require_owner(owner_user_id)
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError(experiment_id)
    if experiment.sample is None or experiment.sample.owner_user_id != owner_user_id:
        raise ExperimentNotFoundError(experiment_id)
    return experiment


def list_owner_experiments(
    db: Session, sample_id: str, owner_user_id: str
) -> list[Experiment]:
    """Full experiment rows (including stored analysis) for one owned sample."""
    get_sample(db, sample_id, owner_user_id)
    return list(
        db.scalars(
            select(Experiment)
            .where(Experiment.sample_id == sample_id)
            .order_by(Experiment.uploaded_at.asc())
        ).all()
    )


def claim_unowned_samples(db: Session, owner_user_id: str) -> int:
    """Assign every ownerless (pre-ownership) sample to ``owner_user_id``.

    Never reassigns samples that already have an owner. Returns the number claimed.
    """
    owner_user_id = _require_owner(owner_user_id)
    result = db.execute(
        update(Sample)
        .where(Sample.owner_user_id.is_(None))
        .values(owner_user_id=owner_user_id)
    )
    db.commit()
    return int(result.rowcount or 0)


def create_magnetometry_experiment(
    db: Session,
    sample_id: str,
    original_filename: str,
    content: bytes,
    user_confirmed_mass_mg: Optional[float] = None,
    *,
    owner_user_id: str,
) -> Experiment:
    get_sample(db, sample_id, owner_user_id)

    text = content.decode("utf-8", errors="ignore")
    if not is_quantum_design_dat(text):
        raise InvalidMagnetometryUploadError(
            "This is not a recognized Quantum Design .DAT file."
        )

    analysis = analyze_quantum_design_magnetometry(
        text,
        filename=original_filename,
        user_confirmed_mass_mg=user_confirmed_mass_mg,
    )
    stored = jsonable_encoder(analysis)
    stored["analysis_version"] = MAGNETOMETRY_PIPELINE_VERSION

    experiment_id = str(uuid4())
    relative_path = write_original_dat(experiment_id, content)

    experiment = Experiment(
        id=experiment_id,
        sample_id=sample_id,
        experiment_type=EXPERIMENT_TYPE_MAGNETOMETRY,
        original_filename=original_filename,
        uploaded_at=datetime.now(timezone.utc),
        raw_file_path=relative_path,
        analysis_version=MAGNETOMETRY_PIPELINE_VERSION,
        analysis_json=stored,
        user_confirmed_mass_mg=user_confirmed_mass_mg,
    )
    try:
        db.add(experiment)
        sample = get_sample(db, sample_id, owner_user_id)
        sample.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(experiment)
    except Exception:
        db.rollback()
        remove_experiment_directory(experiment_id)
        raise

    return experiment


def create_xrd_experiment(
    db: Session,
    sample_id: str,
    original_filename: str,
    content: bytes,
    *,
    owner_user_id: str,
) -> Experiment:
    get_sample(db, sample_id, owner_user_id)

    analysis = analyze_xrd_bytes(content, original_filename)
    stored = jsonable_encoder(analysis)
    stored["analysis_version"] = XRD_PIPELINE_VERSION

    experiment_id = str(uuid4())
    suffix = suffix_for_xrd_filename(original_filename)
    relative_path = write_original_file(experiment_id, content, suffix)

    experiment = Experiment(
        id=experiment_id,
        sample_id=sample_id,
        experiment_type=EXPERIMENT_TYPE_XRD,
        original_filename=original_filename,
        uploaded_at=datetime.now(timezone.utc),
        raw_file_path=relative_path,
        analysis_version=XRD_PIPELINE_VERSION,
        analysis_json=stored,
        user_confirmed_mass_mg=None,
    )
    try:
        db.add(experiment)
        sample = get_sample(db, sample_id, owner_user_id)
        sample.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(experiment)
    except Exception:
        db.rollback()
        remove_experiment_directory(experiment_id)
        raise

    return experiment


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
