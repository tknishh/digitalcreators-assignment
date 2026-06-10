from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import settings


def validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(settings.allowed_extensions))}"
            ),
        )
    return ext


def validate_content_type(content_type: str | None, extension: str | None = None) -> None:
    if not content_type:
        return

    base_type = content_type.split(";")[0].strip().lower()
    if base_type in settings.allowed_mime_types:
        return

    # Browsers/OSes report inconsistent video MIME types; trust validated extensions.
    if base_type.startswith("video/") and extension in settings.allowed_extensions:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported content type: {content_type}",
    )


async def validate_upload_batch(files: list[UploadFile]) -> None:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one video file is required.",
        )

    if len(files) > settings.max_videos_per_job:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.max_videos_per_job} videos allowed per job.",
        )

    total_size = 0
    for upload in files:
        if not upload.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each upload must include a filename.",
            )
        ext = validate_extension(upload.filename)
        validate_content_type(upload.content_type, extension=ext)

        content = await upload.read()
        size = len(content)
        await upload.seek(0)

        if size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{upload.filename}' is empty.",
            )
        if size > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"File '{upload.filename}' exceeds max size of "
                    f"{settings.max_file_size_mb}MB."
                ),
            )
        total_size += size

    if total_size > settings.max_total_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Total upload size exceeds {settings.max_total_size_mb}MB limit.",
        )
