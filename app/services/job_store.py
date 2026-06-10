import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.models import Job
from app.services.storage import cleanup_job_files


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: Job) -> Job:
        async with self._lock:
            self._jobs[job.id] = job
            return job

    async def get(self, job_id: str) -> Optional[Job]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job: Job) -> Job:
        async with self._lock:
            job.touch()
            self._jobs[job.id] = job
            return job

    async def delete(self, job_id: str) -> None:
        async with self._lock:
            self._jobs.pop(job_id, None)
        cleanup_job_files(job_id)

    async def cleanup_expired(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.job_ttl_hours)
        expired_ids: list[str] = []

        async with self._lock:
            for job_id, job in self._jobs.items():
                if job.created_at < cutoff:
                    expired_ids.append(job_id)
            for job_id in expired_ids:
                self._jobs.pop(job_id, None)

        for job_id in expired_ids:
            cleanup_job_files(job_id)

        return len(expired_ids)


job_store = JobStore()
