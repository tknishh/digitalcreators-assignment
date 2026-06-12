import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCheckpoint(str, enum.Enum):
    CREATED = "created"
    UPLOADED = "uploaded"
    ANALYZED = "analyzed"
    CLIPS_SELECTED = "clips_selected"
    CLIPS_EXTRACTED = "clips_extracted"
    STITCHED = "stitched"
    AUDIO_ADDED = "audio_added"
    COMPLETED = "completed"


class Orientation(str, enum.Enum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"


class QualityProfile(str, enum.Enum):
    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.PENDING.value, index=True)
    checkpoint: Mapped[str] = mapped_column(String(30), default=JobCheckpoint.CREATED.value)
    duration_sec: Mapped[float] = mapped_column(Float, default=15.0)
    orientation: Mapped[str] = mapped_column(String(20), default=Orientation.LANDSCAPE.value)
    quality_profile: Mapped[str] = mapped_column(String(20), default=QualityProfile.FAST.value)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_storage_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    output_duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clip_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    analysis_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_clips_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_clip_keys_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stitched_storage_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    inputs: Mapped[list["InputVideoRecord"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class InputVideoRecord(Base):
    __tablename__ = "input_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    job: Mapped["JobRecord"] = relationship(back_populates="inputs")
