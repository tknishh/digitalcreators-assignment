from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class UploadedVideo:
    filename: str
    path: Path
    size_bytes: int
    duration_sec: Optional[float] = None


@dataclass
class Job:
    id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    uploaded_videos: list[UploadedVideo] = field(default_factory=list)
    output_path: Optional[Path] = None
    target_duration_sec: float = 60.0
    progress: int = 0
    error_message: Optional[str] = None
    output_duration_sec: Optional[float] = None
    clip_count: int = 0

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
