from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Video Stitcher API"
    debug: bool = False

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

    # Job lifecycle
    job_ttl_hours: int = 24
    cleanup_interval_minutes: int = 60

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_total_size_bytes(self) -> int:
        return self.max_total_size_mb * 1024 * 1024


settings = Settings()
