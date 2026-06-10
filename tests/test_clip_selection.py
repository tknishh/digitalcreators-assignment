from pathlib import Path
from unittest.mock import patch

import pytest

from app.models import UploadedVideo
from app.services.video_processor import (
    VideoProcessingError,
    compute_target_duration,
    select_clips,
)


def _video(name: str, duration: float) -> UploadedVideo:
    return UploadedVideo(filename=name, path=Path(f"/tmp/{name}"), size_bytes=1000, duration_sec=duration)


def test_compute_target_duration_clamps_to_range():
    short = [_video("a.mp4", 5)]
    assert compute_target_duration(short) == 10.0

    long_sources = [_video(f"v{i}.mp4", 120) for i in range(10)]
    target = compute_target_duration(long_sources)
    assert 10.0 <= target <= 120.0


def test_select_clips_returns_non_empty():
    videos = [_video("a.mp4", 30), _video("b.mp4", 45)]
    clips = select_clips(videos, target_duration_sec=20.0)
    assert clips
    total = sum(c[2] for c in clips)
    assert total >= 10.0


def test_select_clips_raises_on_empty():
    with pytest.raises(VideoProcessingError):
        select_clips([], target_duration_sec=20.0)


def test_select_clips_skips_too_short_videos():
    videos = [_video("tiny.mp4", 0.5), _video("ok.mp4", 20)]
    with patch("app.services.video_processor.probe_duration", return_value=20.0):
        clips = select_clips(videos, target_duration_sec=12.0)
    assert clips
