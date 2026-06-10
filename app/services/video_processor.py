import asyncio
import json
import logging
import random
import subprocess
from pathlib import Path
from typing import Callable, Optional

from app.config import settings
from app.models import Job, JobStatus, UploadedVideo
from app.services import storage

logger = logging.getLogger(__name__)

# Normalized output spec — all clips must match for reliable concat
_OUTPUT_SCALE = (
    f"scale={settings.output_width}:{settings.output_height}:"
    "force_original_aspect_ratio=decrease,"
    f"pad={settings.output_width}:{settings.output_height}:"
    "(ow-iw)/2:(oh-ih)/2,"
    f"fps={settings.output_fps},format=yuv420p,setsar=1"
)


class VideoProcessingError(Exception):
    pass


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise VideoProcessingError(result.stderr.strip() or "FFmpeg command failed")
    return result


def check_ffmpeg_available() -> bool:
    try:
        _run_command(["ffmpeg", "-version"])
        return True
    except (VideoProcessingError, FileNotFoundError):
        return False


def probe_has_audio(video_path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and "audio" in result.stdout


def probe_duration(video_path: Path) -> float:
    result = _run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]
    )
    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    if duration <= 0:
        raise VideoProcessingError(f"Video has zero or invalid duration: {video_path.name}")
    return duration


def probe_durations(videos: list[UploadedVideo]) -> list[UploadedVideo]:
    for video in videos:
        video.duration_sec = probe_duration(video.path)
    return videos


def compute_target_duration(videos: list[UploadedVideo]) -> float:
    """Pick a target duration based on available source material."""
    total_source = sum(v.duration_sec or 0 for v in videos)
    if total_source <= settings.min_output_duration_sec:
        return settings.min_output_duration_sec

    target = total_source * 0.4
    target = max(settings.min_output_duration_sec, min(settings.max_output_duration_sec, target))
    return round(target, 1)


def select_clips(
    videos: list[UploadedVideo],
    target_duration_sec: float,
) -> list[tuple[Path, float, float]]:
    """
    Round-robin clip selection from random start points in each source video.

    Returns list of (path, start_sec, duration_sec) tuples.
    """
    if not videos:
        raise VideoProcessingError("No videos available for clip selection")

    clip_duration = settings.clip_duration_sec
    clips_needed = max(1, int(target_duration_sec / clip_duration))
    selected: list[tuple[Path, float, float]] = []
    video_index = 0
    attempts = 0
    max_attempts = clips_needed * len(videos) * 3

    while len(selected) < clips_needed and attempts < max_attempts:
        video = videos[video_index % len(videos)]
        duration = video.duration_sec or probe_duration(video.path)

        if duration < settings.min_clip_duration_sec:
            video_index += 1
            attempts += 1
            continue

        actual_clip = min(clip_duration, duration)
        max_start = max(0.0, duration - actual_clip)
        start = random.uniform(0, max_start) if max_start > 0 else 0.0

        selected.append((video.path, start, actual_clip))
        video_index += 1
        attempts += 1

    if not selected:
        raise VideoProcessingError("Could not select any valid clips from uploaded videos")

    total = sum(c[2] for c in selected)
    while total > target_duration_sec and selected:
        last_path, last_start, last_dur = selected.pop()
        excess = total - target_duration_sec
        new_dur = max(settings.min_clip_duration_sec, last_dur - excess)
        if new_dur >= settings.min_clip_duration_sec:
            selected.append((last_path, last_start, new_dur))
        total = sum(c[2] for c in selected)

    total = sum(c[2] for c in selected)
    idx = 0
    while total < settings.min_output_duration_sec and idx < max_attempts:
        video = videos[idx % len(videos)]
        duration = video.duration_sec or probe_duration(video.path)
        needed = settings.min_output_duration_sec - total
        clip_len = min(settings.clip_duration_sec, duration, needed)
        if clip_len >= settings.min_clip_duration_sec:
            max_start = max(0.0, duration - clip_len)
            start = random.uniform(0, max_start) if max_start > 0 else 0.0
            selected.append((video.path, start, clip_len))
            total += clip_len
        idx += 1

    return selected


def extract_clip(source: Path, start: float, duration: float, output: Path) -> None:
    """
    Extract and normalize a clip to a consistent format (resolution, fps, audio).

    All clips share the same encoding params so concat plays without frozen frames.
    """
    has_audio = probe_has_audio(source)
    encode_args = [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        str(settings.output_audio_rate),
        "-ac",
        "2",
        "-vsync",
        "cfr",
        "-r",
        str(settings.output_fps),
        "-movflags",
        "+faststart",
        "-avoid_negative_ts",
        "make_zero",
        "-fflags",
        "+genpts",
    ]

    if has_audio:
        _run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-vf",
                _OUTPUT_SCALE,
                "-af",
                f"aresample={settings.output_audio_rate},aformat=channel_layouts=stereo",
                *encode_args,
                str(output),
            ]
        )
    else:
        # AVI and some webm files have no audio — inject silent track
        _run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=stereo:sample_rate={settings.output_audio_rate}",
                "-vf",
                _OUTPUT_SCALE,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
                *encode_args,
                str(output),
            ]
        )


def concat_clips(clip_paths: list[Path], output: Path) -> None:
    """
    Concatenate normalized clips. Always re-encode with genpts — never stream-copy,
    which causes frozen frames at clip boundaries when timestamps drift.
    """
    concat_file = output.parent / "concat_list.txt"
    concat_file.write_text(
        "\n".join(f"file '{path.resolve()}'" for path in clip_paths),
        encoding="utf-8",
    )
    try:
        _run_command(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                str(settings.output_audio_rate),
                "-ac",
                "2",
                "-vsync",
                "cfr",
                "-r",
                str(settings.output_fps),
                "-fflags",
                "+genpts",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
    finally:
        concat_file.unlink(missing_ok=True)


def enforce_duration_bounds(output: Path, target_max: float) -> float:
    duration = probe_duration(output)
    if duration <= settings.max_output_duration_sec:
        return duration

    trimmed = output.parent / f"{output.stem}_trimmed.mp4"
    _run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(output),
            "-t",
            str(settings.max_output_duration_sec),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(trimmed),
        ]
    )
    trimmed.replace(output)
    return probe_duration(output)


async def process_job(
    job: Job,
    on_progress: Optional[Callable[[int], None]] = None,
) -> Job:
    temp_dir = storage.job_temp_dir(job.id)
    output_path = storage.job_output_path(job.id)

    try:
        if on_progress:
            on_progress(5)

        videos = await asyncio.to_thread(probe_durations, job.uploaded_videos)
        job.uploaded_videos = videos
        job.target_duration_sec = compute_target_duration(videos)

        if on_progress:
            on_progress(15)

        clips = await asyncio.to_thread(select_clips, videos, job.target_duration_sec)
        job.clip_count = len(clips)

        clip_paths: list[Path] = []
        for index, (source, start, duration) in enumerate(clips):
            clip_path = temp_dir / f"clip_{index:03d}.mp4"
            await asyncio.to_thread(extract_clip, source, start, duration, clip_path)
            clip_paths.append(clip_path)
            if on_progress:
                progress = 15 + int((index + 1) / len(clips) * 60)
                on_progress(min(progress, 75))

        if on_progress:
            on_progress(80)

        await asyncio.to_thread(concat_clips, clip_paths, output_path)

        if on_progress:
            on_progress(90)

        final_duration = await asyncio.to_thread(
            enforce_duration_bounds, output_path, job.target_duration_sec
        )

        if final_duration < settings.min_output_duration_sec:
            raise VideoProcessingError(
                f"Output duration {final_duration:.1f}s is below minimum "
                f"{settings.min_output_duration_sec}s"
            )

        job.output_path = output_path
        job.output_duration_sec = final_duration
        job.status = JobStatus.COMPLETED
        job.progress = 100

        if on_progress:
            on_progress(100)

        return job

    except Exception as exc:
        logger.exception("Job %s failed: %s", job.id, exc)
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
        raise
