import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_low_memory_mode() -> bool:
    return os.getenv("RENDER") == "true" or os.getenv("LOW_MEMORY_MODE", "").lower() in (
        "1",
        "true",
        "yes",
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Video Stitcher API"
    debug: bool = False
    low_memory_mode: bool = _default_low_memory_mode()

    # Storage
    data_dir: Path = Path("data")
    uploads_dir: Path = Path("data/uploads")
    outputs_dir: Path = Path("data/outputs")
    temp_dir: Path = Path("data/temp")

    # Upload limits
    max_videos_per_job: int = 50
    max_file_size_mb: int = 100
    max_total_size_mb: int = 500
    allowed_extensions: set[str] = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
    allowed_mime_types: set[str] = {
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "video/avi",
        "video/x-msvideo",
        "video/x-matroska",
        "application/octet-stream",
    }

    # Video generation
    min_output_duration_sec: float = 10.0
    max_output_duration_sec: float = 120.0
    default_target_duration_sec: float = 60.0
    clip_duration_sec: float = 4.0
    min_clip_duration_sec: float = 2.0
    output_width: int = 1280
    output_height: int = 720
    output_fps: int = 30
    output_audio_rate: int = 44100
    ffmpeg_preset: str = "fast"
    ffmpeg_threads: int = 0  # 0 = ffmpeg default

    # Job lifecycle
    job_ttl_hours: int = 24
    cleanup_interval_minutes: int = 60

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_total_size_bytes(self) -> int:
        return self.max_total_size_mb * 1024 * 1024

    def model_post_init(self, __context: object) -> None:
        if self.low_memory_mode:
            self.output_width = 640
            self.output_height = 360
            self.output_fps = 24
            self.ffmpeg_preset = "ultrafast"
            self.ffmpeg_threads = 1


settings = Settings()
