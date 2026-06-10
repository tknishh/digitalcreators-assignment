import shutil
from pathlib import Path

from app.config import settings


def ensure_directories() -> None:
    for directory in (
        settings.data_dir,
        settings.uploads_dir,
        settings.outputs_dir,
        settings.temp_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def job_upload_dir(job_id: str) -> Path:
    path = settings.uploads_dir / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_temp_dir(job_id: str) -> Path:
    path = settings.temp_dir / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_output_path(job_id: str) -> Path:
    return settings.outputs_dir / f"{job_id}.mp4"


def cleanup_job_files(job_id: str) -> None:
    for base in (settings.uploads_dir, settings.temp_dir, settings.outputs_dir):
        target = base / job_id if base != settings.outputs_dir else base / f"{job_id}.mp4"
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.is_file():
            target.unlink(missing_ok=True)
