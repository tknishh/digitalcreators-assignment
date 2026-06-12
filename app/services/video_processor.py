import json
import logging
import shutil
import subprocess
from pathlib import Path

from app.config import settings
from app.services.encode_settings import get_encode_settings

logger = logging.getLogger(__name__)


class VideoProcessingError(Exception):
    pass


def check_ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def probe_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(json.loads(result.stdout)["format"]["duration"])
    if duration <= 0:
        raise VideoProcessingError(f"Invalid duration for {video_path.name}")
    return duration


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


def _scale_filter(width: int, height: int) -> str:
    encode = get_encode_settings()
    scale_flags = f":{encode.ffmpeg_scale_flags}" if encode.ffmpeg_scale_flags else ""
    return f"scale={width}:{height}:force_original_aspect_ratio=decrease{scale_flags}"


def _output_scale_filter(width: int, height: int) -> str:
    # Scale + light color normalization for cohesive look across sources
    return (
        f"{_scale_filter(width, height)},"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={settings.output_fps},"
        f"eq=contrast=1.05:brightness=0.02:saturation=1.08,"
        f"format=yuv420p,setsar=1"
    )


def pick_transition_style(merge_index: int) -> str:
    """Rotate through configured transition styles for visual variety."""
    styles = settings.transition_style_list
    return styles[(merge_index - 1) % len(styles)]


def _thread_args() -> list[str]:
    if settings.ffmpeg_threads > 0:
        return ["-threads", str(settings.ffmpeg_threads)]
    return []


def _encode_args(*, with_faststart: bool = True) -> list[str]:
    encode = get_encode_settings()
    args = [
        *_thread_args(),
        "-c:v",
        "libx264",
        "-preset",
        encode.ffmpeg_preset,
        "-crf",
        str(encode.ffmpeg_crf),
        "-c:a",
        "aac",
        "-b:a",
        encode.ffmpeg_audio_bitrate,
        "-ar",
        str(settings.output_audio_rate),
        "-ac",
        "2",
        "-vsync",
        "cfr",
        "-r",
        str(settings.output_fps),
        "-avoid_negative_ts",
        "make_zero",
        "-fflags",
        "+genpts",
    ]
    if with_faststart:
        args.extend(["-movflags", "+faststart"])
    return args


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise VideoProcessingError(result.stderr.strip() or "FFmpeg failed")


def _transition_duration(path_a: Path, path_b: Path) -> float:
    """Pick a safe crossfade length for two clips."""
    max_transition = settings.transition_duration_sec
    dur_a = probe_duration(path_a)
    dur_b = probe_duration(path_b)
    return min(max_transition, dur_a / 2, dur_b / 2, 1.0)


def extract_clip(
    source: Path,
    start: float,
    duration: float,
    output: Path,
    width: int,
    height: int,
) -> None:
    """Fast input-seek + normalize clip to consistent output format."""
    scale = _output_scale_filter(width, height)
    encode_args = _encode_args()
    has_audio = probe_has_audio(source)

    base = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration)]

    if has_audio:
        _run_ffmpeg(
            [
                *base,
                "-vf",
                scale,
                "-af",
                f"aresample={settings.output_audio_rate},aformat=channel_layouts=stereo",
                *encode_args,
                str(output),
            ]
        )
    else:
        _run_ffmpeg(
            [
                *base,
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=stereo:sample_rate={settings.output_audio_rate}",
                "-vf",
                scale,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
                *encode_args,
                str(output),
            ]
        )


def merge_clips_with_transition(
    path_a: Path,
    path_b: Path,
    output: Path,
    *,
    merge_index: int = 1,
) -> None:
    """Crossfade two normalized clips (video + audio). Final audio is replaced later."""
    transition = _transition_duration(path_a, path_b)
    if transition <= 0.05:
        concat_two_hard(path_a, path_b, output)
        return

    dur_a = probe_duration(path_a)
    offset = max(0.0, dur_a - transition)
    style = pick_transition_style(merge_index)
    logger.debug("Merging clips with transition=%s (index=%d)", style, merge_index)

    filter_complex = (
        f"[0:v][1:v]xfade=transition={style}:duration={transition:.3f}:offset={offset:.3f}[vout];"
        f"[0:a][1:a]acrossfade=d={transition:.3f}:c1=tri:c2=tri[aout]"
    )

    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path_a),
            "-i",
            str(path_b),
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            *_encode_args(with_faststart=True),
            str(output),
        ]
    )


def concat_two_hard(path_a: Path, path_b: Path, output: Path) -> None:
    """Hard-cut concat fallback."""
    concat_file = output.parent / "concat_pair.txt"
    concat_file.write_text(
        f"file '{path_a.resolve()}'\nfile '{path_b.resolve()}'",
        encoding="utf-8",
    )
    try:
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
    except VideoProcessingError:
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                *_encode_args(with_faststart=True),
                str(output),
            ]
        )
    finally:
        concat_file.unlink(missing_ok=True)


def concat_clips(clip_paths: list[Path], output: Path) -> None:
    if not clip_paths:
        raise VideoProcessingError("No clips to concatenate")
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], output)
        return

    working = clip_paths[0]
    temp_dir = output.parent
    for index, next_clip in enumerate(clip_paths[1:], start=1):
        merged = temp_dir / f"merge_{index:03d}.mp4"
        if settings.enable_transitions:
            merge_clips_with_transition(working, next_clip, merged, merge_index=index)
        else:
            concat_two_hard(working, next_clip, merged)
        if working != clip_paths[0]:
            working.unlink(missing_ok=True)
        next_clip.unlink(missing_ok=True)
        working = merged
    shutil.move(str(working), str(output))


def mux_audio_video(video_path: Path, audio_path: Path, output: Path) -> None:
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def enforce_max_duration(output: Path, max_duration: float) -> float:
    duration = probe_duration(output)
    if duration <= max_duration:
        return duration
    trimmed = output.parent / f"{output.stem}_trimmed.mp4"
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(output),
            "-t",
            str(max_duration),
            *_encode_args(),
            str(trimmed),
        ]
    )
    trimmed.replace(output)
    return probe_duration(output)


def estimate_clips_needed(target_duration_sec: float) -> int:
    """Account for crossfade overlap when planning clip count."""
    clip_len = settings.clip_duration_sec
    if not settings.enable_transitions:
        return max(1, int(target_duration_sec / clip_len))

    transition = settings.transition_duration_sec
    # Each transition overlaps ~transition seconds with the prior clip
    effective_per_clip = max(settings.min_clip_duration_sec, clip_len - transition * 0.85)
    return max(1, int(target_duration_sec / effective_per_clip) + 1)
