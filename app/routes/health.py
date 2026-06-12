from fastapi import APIRouter

from app.config import settings
from app.schemas import HealthResponse
from app.services.object_storage import get_active_storage_backend, get_object_storage
from app.services.video_processor import check_ffmpeg_available

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    get_object_storage()
    return HealthResponse(
        status="ok",
        ffmpeg_available=check_ffmpeg_available(),
        storage_backend=get_active_storage_backend(),
    )
