import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import InputVideoRecord, JobCheckpoint, JobRecord, JobStatus
from app.services.object_storage import ObjectStorage, get_object_storage

logger = logging.getLogger(__name__)

_MISSING_INPUTS_MSG = (
    "Input files are missing from storage (likely from a previous container run). "
    "Please create a new job and upload again."
)


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_job(
        self,
        duration_sec: float,
        orientation: str,
        prompt: Optional[str],
        quality_profile: str = "fast",
    ) -> JobRecord:
        job = JobRecord(
            duration_sec=duration_sec,
            orientation=orientation,
            quality_profile=quality_profile,
            prompt=prompt,
            status=JobStatus.PENDING.value,
            checkpoint=JobCheckpoint.CREATED.value,
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def add_input(
        self,
        job_id: str,
        filename: str,
        storage_key: str,
        size_bytes: int,
        duration_sec: Optional[float] = None,
    ) -> InputVideoRecord:
        record = InputVideoRecord(
            job_id=job_id,
            filename=filename,
            storage_key=storage_key,
            size_bytes=size_bytes,
            duration_sec=duration_sec,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        stmt = (
            select(JobRecord)
            .options(joinedload(JobRecord.inputs))
            .where(JobRecord.id == job_id)
        )
        return self.session.scalars(stmt).unique().first()

    def update_job(self, job: JobRecord) -> JobRecord:
        job.updated_at = datetime.now(timezone.utc)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def set_checkpoint(self, job: JobRecord, checkpoint: JobCheckpoint, progress: int) -> JobRecord:
        job.checkpoint = checkpoint.value
        job.progress = progress
        return self.update_job(job)

    def _inputs_available(self, job: JobRecord, storage: ObjectStorage) -> bool:
        if not job.inputs:
            return False
        return all(storage.exists(inp.storage_key) for inp in job.inputs)

    def _load_job_with_inputs(self, job_id: str) -> Optional[JobRecord]:
        return self.get_job(job_id)

    def get_next_pending_job(self) -> Optional[JobRecord]:
        storage = get_object_storage()

        processing = self.session.scalars(
            select(JobRecord).where(JobRecord.status == JobStatus.PROCESSING.value)
        ).first()
        if processing:
            job = self._load_job_with_inputs(processing.id)
            if job and self._inputs_available(job, storage):
                return job
            if job:
                logger.warning("Marking interrupted job %s as failed — inputs missing", job.id)
                self.mark_failed(job, _MISSING_INPUTS_MSG)

        pending_jobs = self.session.scalars(
            select(JobRecord)
            .where(JobRecord.status == JobStatus.PENDING.value)
            .order_by(JobRecord.created_at.asc())
        ).all()

        for pending in pending_jobs:
            job = self._load_job_with_inputs(pending.id)
            if not job:
                continue
            if self._inputs_available(job, storage):
                return job
            logger.warning("Marking stale job %s as failed — inputs missing", job.id)
            self.mark_failed(job, _MISSING_INPUTS_MSG)

        return None

    def mark_failed(self, job: JobRecord, message: str) -> JobRecord:
        job.status = JobStatus.FAILED.value
        job.error_message = message
        return self.update_job(job)

    def mark_completed(self, job: JobRecord) -> JobRecord:
        job.status = JobStatus.COMPLETED.value
        job.checkpoint = JobCheckpoint.COMPLETED.value
        job.progress = 100
        return self.update_job(job)

    def save_json_field(self, job: JobRecord, field: str, data: object) -> JobRecord:
        setattr(job, field, json.dumps(data))
        return self.update_job(job)

    def load_json_field(self, job: JobRecord, field: str) -> object:
        raw = getattr(job, field)
        return json.loads(raw) if raw else None

    def cleanup_expired(self, ttl_hours: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        jobs = self.session.scalars(
            select(JobRecord).where(JobRecord.created_at < cutoff)
        ).all()
        count = len(jobs)
        for job in jobs:
            self.session.delete(job)
        self.session.commit()
        return count
