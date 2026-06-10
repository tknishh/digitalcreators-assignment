import asyncio
import logging
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.config import settings
from app.models import Job, JobStatus, UploadedVideo
from app.schemas import JobCreateResponse, JobStatusResponse
from app.services.job_store import job_store
from app.services.storage import job_upload_dir
from app.services.video_processor import VideoProcessingError, process_job
from app.validation import validate_upload_batch

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


async def _save_uploads(job_id: str, files: list[UploadFile]) -> list[UploadedVideo]:
    upload_dir = job_upload_dir(job_id)
    saved: list[UploadedVideo] = []

    for index, upload in enumerate(files):
        assert upload.filename
        safe_name = f"{index:03d}_{Path(upload.filename).name}"
        dest = upload_dir / safe_name

        async with aiofiles.open(dest, "wb") as out_file:
            while chunk := await upload.read(1024 * 1024):
                await out_file.write(chunk)

        saved.append(
            UploadedVideo(
                filename=upload.filename,
                path=dest,
                size_bytes=dest.stat().st_size,
            )
        )

    return saved


async def _run_generation(job_id: str) -> None:
    job = await job_store.get(job_id)
    if not job:
        return

    job.status = JobStatus.PROCESSING
    job.progress = 0
    await job_store.update(job)

    def update_progress(value: int) -> None:
        job.progress = value

    try:
        await process_job(job, on_progress=update_progress)
        await job_store.update(job)
    except VideoProcessingError as exc:
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
        await job_store.update(job)
    except Exception as exc:
        logger.exception("Unexpected error processing job %s", job_id)
        job.status = JobStatus.FAILED
        job.error_message = f"Internal processing error: {exc}"
        await job_store.update(job)


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> JobCreateResponse:
    await validate_upload_batch(files)

    job = Job(target_duration_sec=settings.default_target_duration_sec)
    job.uploaded_videos = await _save_uploads(job.id, files)
    await job_store.create(job)

    background_tasks.add_task(_run_generation, job.id)

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        message="Job accepted. Poll GET /api/jobs/{job_id} for status.",
        video_count=len(job.uploaded_videos),
        target_duration_sec=job.target_duration_sec,
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    download_url = None
    if job.status == JobStatus.COMPLETED and job.output_path:
        download_url = f"/api/jobs/{job.id}/download"

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        updated_at=job.updated_at,
        video_count=len(job.uploaded_videos),
        target_duration_sec=job.target_duration_sec,
        output_duration_sec=job.output_duration_sec,
        clip_count=job.clip_count,
        error_message=job.error_message,
        download_url=download_url,
    )


@router.get("/{job_id}/download")
async def download_job_output(job_id: str) -> FileResponse:
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    if job.status != JobStatus.COMPLETED or not job.output_path or not job.output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Output not ready. Current status: {job.status.value}",
        )

    return FileResponse(
        path=job.output_path,
        media_type="video/mp4",
        filename=f"stitched_{job_id[:8]}.mp4",
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str) -> None:
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    await job_store.delete(job_id)
