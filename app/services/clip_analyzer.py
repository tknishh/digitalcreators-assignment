import json
import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services.video_processor import estimate_clips_needed

logger = logging.getLogger(__name__)

_load_lock = threading.Lock()
_MAX_LOAD_ATTEMPTS = 2


@dataclass
class FrameCandidate:
    video_path: str
    storage_key: str
    filename: str
    timestamp_sec: float
    score: float


class ClipAnalyzer:
    """Uses Hugging Face CLIP to score video keyframes against an optional prompt."""

    def __init__(self) -> None:
        self._pipeline = None

    def _model_cache_dir(self) -> Path:
        slug = settings.clip_model_id.replace("/", "--")
        return settings.hf_cache_dir / f"models--{slug}"

    def _clear_model_cache(self) -> None:
        cache_path = self._model_cache_dir()
        if cache_path.exists():
            logger.warning("Clearing corrupted CLIP cache at %s", cache_path)
            shutil.rmtree(cache_path, ignore_errors=True)

    def ensure_loaded(self) -> None:
        """Load CLIP once, thread-safe. Call before parallel analysis."""
        if self._pipeline is not None:
            return
        with _load_lock:
            if self._pipeline is not None:
                return
            import torch
            from transformers import pipeline

            settings.hf_cache_dir.mkdir(parents=True, exist_ok=True)
            last_error: Exception | None = None

            for attempt in range(1, _MAX_LOAD_ATTEMPTS + 1):
                try:
                    logger.info(
                        "Loading CLIP pipeline: %s (attempt %d/%d)",
                        settings.clip_model_id,
                        attempt,
                        _MAX_LOAD_ATTEMPTS,
                    )
                    self._pipeline = pipeline(
                        task="zero-shot-image-classification",
                        model=settings.clip_model_id,
                        device="cpu",
                        torch_dtype=torch.float32,
                        model_kwargs={"cache_dir": str(settings.hf_cache_dir)},
                    )
                    return
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    last_error = exc
                    logger.warning("CLIP load failed: %s", exc)
                    if attempt < _MAX_LOAD_ATTEMPTS:
                        self._clear_model_cache()

            raise RuntimeError(
                f"Failed to load CLIP model after {_MAX_LOAD_ATTEMPTS} attempts"
            ) from last_error

    def _extract_keyframe(self, video_path: Path, timestamp_sec: float, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(timestamp_sec),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "Keyframe extraction failed")

    def _probe_duration(self, video_path: Path) -> float:
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
            check=False,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])

    def _score_frame(self, frame_path: Path, texts: list[str]) -> float:
        from PIL import Image

        self.ensure_loaded()
        assert self._pipeline is not None
        image = Image.open(frame_path).convert("RGB")
        with _load_lock:
            results = self._pipeline(image, candidate_labels=texts)
        primary = texts[0]
        for item in results:
            if item["label"] == primary:
                return float(item["score"])
        return float(results[0]["score"]) if results else 0.0

    def analyze_video(
        self,
        video_path: Path,
        storage_key: str,
        filename: str,
        prompt: str | None,
        temp_dir: Path,
    ) -> list[FrameCandidate]:
        duration = self._probe_duration(video_path)
        interval = settings.keyframe_interval_sec
        timestamps: list[float] = []
        t = interval / 2
        while t < duration:
            timestamps.append(t)
            t += interval
        if not timestamps:
            timestamps = [0.0]

        if prompt:
            texts = [
                prompt,
                f"cinematic footage matching: {prompt}",
                "professional high quality video content",
            ]
        else:
            texts = [
                "dynamic interesting video scene",
                "high quality cinematic shot",
                "engaging visual content",
            ]

        candidates: list[FrameCandidate] = []
        for idx, ts in enumerate(timestamps):
            frame_path = temp_dir / f"{storage_key.replace('/', '_')}_{idx}.jpg"
            try:
                self._extract_keyframe(video_path, ts, frame_path)
                score = self._score_frame(frame_path, texts)
                candidates.append(
                    FrameCandidate(
                        video_path=str(video_path),
                        storage_key=storage_key,
                        filename=filename,
                        timestamp_sec=ts,
                        score=score,
                    )
                )
            except RuntimeError:
                logger.warning("Skipping keyframe at %.1fs for %s", ts, filename)
            finally:
                frame_path.unlink(missing_ok=True)

        return candidates

    def _rank_candidates(
        self,
        all_candidates: list[FrameCandidate],
        prompt: str | None,
    ) -> list[FrameCandidate]:
        """Build an ordered candidate list — prompt mode interleaves sources for pacing."""
        if not prompt:
            by_video: dict[str, list[FrameCandidate]] = {}
            for c in all_candidates:
                by_video.setdefault(c.storage_key, []).append(c)
            ranked: list[FrameCandidate] = []
            max_len = max(len(v) for v in by_video.values())
            for i in range(max_len):
                for key in sorted(by_video.keys()):
                    if i < len(by_video[key]):
                        ranked.append(by_video[key][i])
            return ranked

        by_video: dict[str, list[FrameCandidate]] = {}
        for c in all_candidates:
            by_video.setdefault(c.storage_key, []).append(c)
        for clips in by_video.values():
            clips.sort(key=lambda x: x.score, reverse=True)

        ranked = []
        max_len = max(len(v) for v in by_video.values())
        for i in range(max_len):
            round_clips = [by_video[k][i] for k in sorted(by_video.keys()) if i < len(by_video[k])]
            round_clips.sort(key=lambda x: x.score, reverse=True)
            ranked.extend(round_clips)
        return ranked

    def select_clips(
        self,
        all_candidates: list[FrameCandidate],
        target_duration_sec: float,
        prompt: str | None,
    ) -> list[dict]:
        if not all_candidates:
            return []

        clip_len = settings.clip_duration_sec
        clips_needed = estimate_clips_needed(target_duration_sec)
        ranked = self._rank_candidates(all_candidates, prompt)

        selected: list[dict] = []
        last_source: str | None = None

        for candidate in ranked:
            if len(selected) >= clips_needed:
                break
            # Avoid back-to-back clips from the same source when prompt-driven
            if prompt and candidate.storage_key == last_source and len(selected) >= 1:
                continue
            start = max(0.0, candidate.timestamp_sec - clip_len / 2)
            selected.append(
                {
                    "storage_key": candidate.storage_key,
                    "filename": candidate.filename,
                    "start_sec": round(start, 2),
                    "duration_sec": clip_len,
                    "score": round(candidate.score, 4),
                }
            )
            last_source = candidate.storage_key

        # Fill remaining slots if interleave skip left gaps
        if len(selected) < clips_needed:
            for candidate in sorted(all_candidates, key=lambda c: c.score, reverse=True):
                if len(selected) >= clips_needed:
                    break
                if any(s["storage_key"] == candidate.storage_key and s["start_sec"] == round(
                    max(0.0, candidate.timestamp_sec - clip_len / 2), 2
                ) for s in selected):
                    continue
                selected.append(
                    {
                        "storage_key": candidate.storage_key,
                        "filename": candidate.filename,
                        "start_sec": round(max(0.0, candidate.timestamp_sec - clip_len / 2), 2),
                        "duration_sec": clip_len,
                        "score": round(candidate.score, 4),
                    }
                )

        # Trim to target (accounting for transition overlap in final stitch)
        transition_overlap = (
            settings.transition_duration_sec * max(0, len(selected) - 1)
            if settings.enable_transitions
            else 0
        )
        total = sum(c["duration_sec"] for c in selected) - transition_overlap
        while total > target_duration_sec and selected:
            selected.pop()
            transition_overlap = (
                settings.transition_duration_sec * max(0, len(selected) - 1)
                if settings.enable_transitions
                else 0
            )
            total = sum(c["duration_sec"] for c in selected) - transition_overlap

        while total < settings.min_output_duration_sec and ranked:
            c = ranked[len(selected) % len(ranked)]
            selected.append(
                {
                    "storage_key": c.storage_key,
                    "filename": c.filename,
                    "start_sec": round(max(0.0, c.timestamp_sec - clip_len / 2), 2),
                    "duration_sec": clip_len,
                    "score": round(c.score, 4),
                }
            )
            transition_overlap = (
                settings.transition_duration_sec * max(0, len(selected) - 1)
                if settings.enable_transitions
                else 0
            )
            total = sum(c["duration_sec"] for c in selected) - transition_overlap

        return selected


_analyzer: ClipAnalyzer | None = None


def get_clip_analyzer() -> ClipAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = ClipAnalyzer()
    return _analyzer
