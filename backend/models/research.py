"""SQLAlchemy models for scientific Sample and Experiment persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Sample(Base):
    __tablename__ = "scientific_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    formula: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="sample")


class Experiment(Base):
    __tablename__ = "scientific_experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sample_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_samples.id"), nullable=False, index=True
    )
    experiment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(32), nullable=False)
    analysis_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    user_confirmed_mass_mg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample: Mapped[Sample] = relationship(back_populates="experiments")
