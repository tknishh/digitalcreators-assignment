from fastapi import APIRouter

from app.schemas import HealthResponse
from app.services.video_processor import check_ffmpeg_available

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ffmpeg_available=check_ffmpeg_available(),
    )
