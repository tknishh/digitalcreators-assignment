import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.routes import health, jobs
from app.services.job_store import job_store
from app.services.storage import ensure_directories
from app.services.video_processor import check_ffmpeg_available

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


async def _cleanup_loop() -> None:
    while True:
        try:
            removed = await job_store.cleanup_expired()
            if removed:
                logger.info("Cleaned up %d expired jobs", removed)
        except Exception:
            logger.exception("Cleanup loop error")
        await asyncio.sleep(settings.cleanup_interval_minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories()
    if not check_ffmpeg_available():
        logger.warning("FFmpeg not found — video processing will fail.")

    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.app_name,
    description="Upload videos and generate a stitched highlight reel.",
    version="1.0.0",
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
        },
    )
