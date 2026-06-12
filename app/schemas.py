from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import JobStatus, Orientation, QualityProfile


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    video_count: int
    duration_sec: float
    orientation: Orientation
    quality_profile: QualityProfile


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    checkpoint: str
    progress: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    video_count: int
    duration_sec: float
    orientation: Orientation
    quality_profile: QualityProfile
    prompt: Optional[str] = None
    output_duration_sec: Optional[float] = None
    clip_count: Optional[int] = None
    error_message: Optional[str] = None
    download_url: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    ffmpeg_available: bool
    storage_backend: str
    version: str = "2.0.0"
