from pathlib import Path

from app.config import settings


def ensure_directories() -> None:
    for directory in (
        settings.data_dir,
        settings.temp_dir,
        settings.local_storage_dir,
        settings.hf_cache_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    if settings.database_url.startswith("sqlite:///./"):
        db_path = settings.database_url.replace("sqlite:///./", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
