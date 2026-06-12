import logging
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import JobCheckpoint, JobStatus, Orientation, QualityProfile
from app.services.encode_settings import VALID_QUALITY_PROFILES
from app.schemas import JobCreateResponse, JobStatusResponse
from app.services.job_repository import JobRepository
from app.services.object_storage import get_object_storage
from app.services.video_processor import probe_duration
from app.validation import validate_upload_batch

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


def _parse_duration(value: float) -> float:
    if value < settings.min_output_duration_sec or value > settings.max_output_duration_sec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"duration_sec must be between {settings.min_output_duration_sec} "
                f"and {settings.max_output_duration_sec}."
            ),
        )
    return value


def _parse_quality_profile(value: str) -> str:
    profile = value.lower().strip()
    if profile not in VALID_QUALITY_PROFILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quality_profile must be 'fast', 'balanced', or 'high'.",
        )
    return profile


def _parse_orientation(value: str) -> str:
    try:
        return Orientation(value.lower()).value
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="orientation must be 'landscape' or 'portrait'.",
        )


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    duration_sec: float = Form(...),
    orientation: str = Form("landscape"),
    quality_profile: str = Form("fast"),
    prompt: Optional[str] = Form(None),
    files: list[UploadFile] = File(...),
) -> JobCreateResponse:
    await validate_upload_batch(files)
    duration_sec = _parse_duration(duration_sec)
    orientation = _parse_orientation(orientation)
    quality_profile = _parse_quality_profile(quality_profile)
    prompt = prompt.strip() if prompt else None

    session = SessionLocal()
    storage = get_object_storage()
    temp_dir = settings.temp_dir / "uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        repo = JobRepository(session)
        job = repo.create_job(
            duration_sec=duration_sec,
            orientation=orientation,
            prompt=prompt,
            quality_profile=quality_profile,
        )

        for index, upload in enumerate(files):
            assert upload.filename
            temp_path = temp_dir / f"{job.id}_{index}_{Path(upload.filename).name}"
            async with aiofiles.open(temp_path, "wb") as out:
                while chunk := await upload.read(1024 * 1024):
                    await out.write(chunk)

            storage_key = f"jobs/{job.id}/inputs/{index:03d}_{Path(upload.filename).name}"
            storage.upload(temp_path, storage_key, content_type=upload.content_type or "video/mp4")

            duration = None
            try:
                duration = probe_duration(temp_path)
            except Exception:
                logger.warning("Could not probe duration for %s", upload.filename)

            repo.add_input(
                job_id=job.id,
                filename=upload.filename,
                storage_key=storage_key,
                size_bytes=temp_path.stat().st_size,
                duration_sec=duration,
            )
            temp_path.unlink(missing_ok=True)

        job = repo.get_job(job.id)
        assert job
        repo.set_checkpoint(job, JobCheckpoint.UPLOADED, 5)

        return JobCreateResponse(
            job_id=job.id,
            status=JobStatus(job.status),
            message="Job queued. Poll GET /api/jobs/{job_id} for status.",
            video_count=len(job.inputs),
            duration_sec=job.duration_sec,
            orientation=Orientation(job.orientation),
            quality_profile=QualityProfile(getattr(job, "quality_profile", None) or "fast"),
        )
    finally:
        session.close()


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        job = repo.get_job(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

        download_url = None
        if job.status == JobStatus.COMPLETED.value and job.output_storage_key:
            download_url = f"/api/jobs/{job.id}/download"

        return JobStatusResponse(
            job_id=job.id,
            status=JobStatus(job.status),
            checkpoint=job.checkpoint,
            progress=job.progress,
            created_at=job.created_at,
            updated_at=job.updated_at,
            video_count=len(job.inputs),
            duration_sec=job.duration_sec,
            orientation=Orientation(job.orientation),
            quality_profile=QualityProfile(getattr(job, "quality_profile", None) or "fast"),
            prompt=job.prompt,
            output_duration_sec=job.output_duration_sec,
            clip_count=job.clip_count,
            error_message=job.error_message,
            download_url=download_url,
        )
    finally:
        session.close()


@router.get("/{job_id}/download")
async def download_job_output(job_id: str) -> FileResponse:
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        job = repo.get_job(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
        if job.status != JobStatus.COMPLETED.value or not job.output_storage_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Output not ready. Current status: {job.status}",
            )

        local_path = settings.temp_dir / f"{job_id}_download.mp4"
        get_object_storage().download(job.output_storage_key, local_path)
        return FileResponse(
            path=local_path,
            media_type="video/mp4",
            filename=f"regenerated_{job_id[:8]}.mp4",
            background=None,
        )
    finally:
        session.close()


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str) -> None:
    session = SessionLocal()
    storage = get_object_storage()
    try:
        repo = JobRepository(session)
        job = repo.get_job(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

        keys = [inp.storage_key for inp in job.inputs]
        if job.output_storage_key:
            keys.append(job.output_storage_key)
        if job.stitched_storage_key:
            keys.append(job.stitched_storage_key)
        clip_keys = repo.load_json_field(job, "extracted_clip_keys_json") or []
        keys.extend(clip_keys)

        for key in keys:
            try:
                storage.delete(key)
            except Exception:
                logger.warning("Failed to delete storage key %s", key)

        session.delete(job)
        session.commit()
    finally:
        session.close()
