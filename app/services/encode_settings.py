"""Per-job FFmpeg encode settings resolved from quality profile."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

QUALITY_PROFILES: dict[str, dict[str, object]] = {
    "fast": {
        "ffmpeg_crf": 23,
        "ffmpeg_preset": "veryfast",
        "ffmpeg_scale_flags": "",
        "ffmpeg_audio_bitrate": "192k",
        "landscape_width": 1280,
        "landscape_height": 720,
        "portrait_width": 720,
        "portrait_height": 1280,
    },
    "balanced": {
        "ffmpeg_crf": 20,
        "ffmpeg_preset": "fast",
        "ffmpeg_scale_flags": "flags=lanczos",
        "ffmpeg_audio_bitrate": "256k",
        "landscape_width": 1280,
        "landscape_height": 720,
        "portrait_width": 720,
        "portrait_height": 1280,
    },
    "high": {
        "ffmpeg_crf": 18,
        "ffmpeg_preset": "medium",
        "ffmpeg_scale_flags": "flags=lanczos+accurate_rnd+full_chroma_int",
        "ffmpeg_audio_bitrate": "320k",
        "landscape_width": 1920,
        "landscape_height": 1080,
        "portrait_width": 1080,
        "portrait_height": 1920,
    },
}

VALID_QUALITY_PROFILES = frozenset(QUALITY_PROFILES.keys())


@dataclass(frozen=True)
class EncodeSettings:
    ffmpeg_crf: int
    ffmpeg_preset: str
    ffmpeg_scale_flags: str
    ffmpeg_audio_bitrate: str
    landscape_width: int
    landscape_height: int
    portrait_width: int
    portrait_height: int

    def dimensions(self, orientation: str) -> tuple[int, int]:
        if orientation == "portrait":
            return self.portrait_width, self.portrait_height
        return self.landscape_width, self.landscape_height


_active: ContextVar[EncodeSettings | None] = ContextVar("active_encode", default=None)


def resolve_quality_profile(profile: str) -> EncodeSettings:
    key = profile.lower()
    if key not in QUALITY_PROFILES:
        key = "fast"
    data = QUALITY_PROFILES[key]
    return EncodeSettings(
        ffmpeg_crf=int(data["ffmpeg_crf"]),
        ffmpeg_preset=str(data["ffmpeg_preset"]),
        ffmpeg_scale_flags=str(data["ffmpeg_scale_flags"]),
        ffmpeg_audio_bitrate=str(data["ffmpeg_audio_bitrate"]),
        landscape_width=int(data["landscape_width"]),
        landscape_height=int(data["landscape_height"]),
        portrait_width=int(data["portrait_width"]),
        portrait_height=int(data["portrait_height"]),
    )


def get_encode_settings() -> EncodeSettings:
    ctx = _active.get()
    if ctx is not None:
        return ctx
    from app.config import settings

    return resolve_quality_profile(settings.video_quality_profile)


@contextmanager
def job_encode_context(quality_profile: str) -> Iterator[EncodeSettings]:
    encode = resolve_quality_profile(quality_profile)
    token = _active.set(encode)
    try:
        yield encode
    finally:
        _active.reset(token)
