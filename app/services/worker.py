import asyncio
import logging

from app.config import settings
from app.db.database import SessionLocal
from app.services.job_repository import JobRepository
from app.services.pipeline import JobPipeline

logger = logging.getLogger(__name__)


class JobWorker:
    """Processes one job at a time with resumable checkpoints."""

    def __init__(self) -> None:
        self._running = False

    async def run_forever(self) -> None:
        self._running = True
        logger.info("Job worker started")
        while self._running:
            try:
                processed = await asyncio.to_thread(self._process_next)
                if not processed:
                    await asyncio.sleep(settings.worker_poll_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker loop error")
                await asyncio.sleep(settings.worker_poll_interval_sec)

    def stop(self) -> None:
        self._running = False

    def _process_next(self) -> bool:
        session = SessionLocal()
        try:
            repo = JobRepository(session)
            job = repo.get_next_pending_job()
            if not job:
                return False

            logger.info("Processing job %s at checkpoint %s", job.id, job.checkpoint)
            pipeline = JobPipeline(repo)
            pipeline.run(job)
            return True
        finally:
            session.close()


worker = JobWorker()
