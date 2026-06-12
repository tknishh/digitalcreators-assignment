import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db.database import init_db
from app.routes import health, jobs
from app.services.job_repository import JobRepository
from app.services.storage import ensure_directories
from app.services.object_storage import get_active_storage_backend, get_object_storage
from app.services.video_processor import check_ffmpeg_available
from app.services.worker import worker
from app.db.database import SessionLocal

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


async def _cleanup_loop() -> None:
    while True:
        try:
            session = SessionLocal()
            try:
                repo = JobRepository(session)
                removed = repo.cleanup_expired(settings.job_ttl_hours)
                if removed:
                    logger.info("Cleaned up %d expired jobs", removed)
            finally:
                session.close()
        except Exception:
            logger.exception("Cleanup loop error")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories()
    init_db()
    if not check_ffmpeg_available():
        logger.warning("FFmpeg not found — video processing will fail.")
    get_object_storage()
    logger.info("Storage backend: %s", get_active_storage_backend())

    worker_task = asyncio.create_task(worker.run_forever())
    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    worker.stop()
    worker_task.cancel()
    cleanup_task.cancel()
    for task in (worker_task, cleanup_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    description="AI-assisted video regeneration with Hugging Face, Firebase, and SQLite.",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(jobs.router)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "max_videos": settings.max_videos_per_job,
            "max_file_mb": settings.max_file_size_mb,
            "max_total_mb": settings.max_total_size_mb,
            "min_duration": int(settings.min_output_duration_sec),
            "max_duration": int(settings.max_output_duration_sec),
            "default_duration": int(settings.default_output_duration_sec),
        },
    )
