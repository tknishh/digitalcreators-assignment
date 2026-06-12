import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_CPU_COUNT = os.cpu_count() or 4


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Video Regenerator API"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./data/jobs.db"

    # Firebase (falls back to local mirror when credentials missing)
    firebase_credentials_path: str = ""
    firebase_storage_bucket: str = ""
    use_local_storage: bool = False

    # Local paths
    data_dir: Path = Path("data")
    temp_dir: Path = Path("data/temp")
    local_storage_dir: Path = Path("data/storage")

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
    default_output_duration_sec: float = 15.0
    clip_duration_sec: float = 4.0
    min_clip_duration_sec: float = 2.0
    enable_transitions: bool = True
    transition_duration_sec: float = 0.5
    # Comma-separated xfade styles, rotated per clip boundary (fade, smoothleft, dissolve, wipeleft, etc.)
    transition_styles: str = "fade,smoothleft,dissolve,wipeleft"
    # fast | balanced | high — sets CRF, preset, resolution, and scale algorithm
    video_quality_profile: str = "fast"
    landscape_width: int = 1280
    landscape_height: int = 720
    portrait_width: int = 720
    portrait_height: int = 1280
    output_fps: int = 30
    output_audio_rate: int = 44100
    ffmpeg_scale_flags: str = ""
    ffmpeg_preset: str = "veryfast"
    ffmpeg_crf: int = 23
    ffmpeg_audio_bitrate: str = "192k"
    ffmpeg_threads: int = max(1, _CPU_COUNT // 2)
    parallel_extract_workers: int = max(2, min(4, _CPU_COUNT // 2))
    parallel_analyze_workers: int = max(2, min(6, _CPU_COUNT))

    # Hugging Face
    clip_model_id: str = "openai/clip-vit-base-patch32"
    musicgen_model_id: str = "facebook/musicgen-small"
    hf_cache_dir: Path = Path("data/hf_cache")
    enable_musicgen: bool = True
    keyframe_interval_sec: float = 2.0

    # Worker
    worker_poll_interval_sec: float = 3.0
    job_ttl_hours: int = 72

    @property
    def transition_style_list(self) -> list[str]:
        styles = [s.strip() for s in self.transition_styles.split(",") if s.strip()]
        return styles or ["fade"]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_total_size_bytes(self) -> int:
        return self.max_total_size_mb * 1024 * 1024

    @property
    def storage_backend(self) -> str:
        if self.use_local_storage or not self.firebase_credentials_path:
            return "local"
        return "firebase"

    def output_dimensions(self, orientation: str) -> tuple[int, int]:
        if orientation == "portrait":
            return self.portrait_width, self.portrait_height
        return self.landscape_width, self.landscape_height


settings = Settings()
