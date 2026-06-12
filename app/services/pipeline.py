import logging
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from app.config import settings
from app.db.models import JobCheckpoint, JobRecord, JobStatus
from app.services.audio_generator import get_audio_generator
from app.services.clip_analyzer import get_clip_analyzer
from app.services.job_repository import JobRepository
from app.services.object_storage import get_object_storage
from app.services.encode_settings import job_encode_context
from app.services.video_processor import (
    VideoProcessingError,
    concat_clips,
    enforce_max_duration,
    extract_clip,
    mux_audio_video,
    probe_duration,
)

logger = logging.getLogger(__name__)

CHECKPOINT_ORDER = [
    JobCheckpoint.CREATED,
    JobCheckpoint.UPLOADED,
    JobCheckpoint.ANALYZED,
    JobCheckpoint.CLIPS_SELECTED,
    JobCheckpoint.CLIPS_EXTRACTED,
    JobCheckpoint.STITCHED,
    JobCheckpoint.AUDIO_ADDED,
    JobCheckpoint.COMPLETED,
]


def _checkpoint_index(checkpoint: str) -> int:
    try:
        return CHECKPOINT_ORDER.index(JobCheckpoint(checkpoint))
    except ValueError:
        return 0


class JobPipeline:
    def __init__(self, repo: JobRepository) -> None:
        self.repo = repo
        self.storage = get_object_storage()
        self.analyzer = get_clip_analyzer()
        self.audio = get_audio_generator()
        self._local_inputs: dict[str, Path] = {}

    def run(self, job: JobRecord) -> None:
        job.status = JobStatus.PROCESSING.value
        self.repo.update_job(job)
        work_dir = settings.temp_dir / job.id
        work_dir.mkdir(parents=True, exist_ok=True)
        quality = getattr(job, "quality_profile", None) or "fast"

        try:
            with job_encode_context(quality):
                self._run_stages(job, work_dir)
        except Exception as exc:
            logger.exception("Pipeline failed for job %s", job.id)
            self.repo.mark_failed(job, str(exc))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            self._local_inputs.clear()

    def _run_stages(self, job: JobRecord, work_dir: Path) -> None:
        checkpoint = JobCheckpoint(job.checkpoint)
        if _checkpoint_index(checkpoint.value) < _checkpoint_index(JobCheckpoint.ANALYZED.value):
            self._stage_analyze(job, work_dir)
        checkpoint = JobCheckpoint(job.checkpoint)

        if _checkpoint_index(checkpoint.value) < _checkpoint_index(
            JobCheckpoint.CLIPS_SELECTED.value
        ):
            self._stage_select_clips(job)
        checkpoint = JobCheckpoint(job.checkpoint)

        if _checkpoint_index(checkpoint.value) < _checkpoint_index(
            JobCheckpoint.CLIPS_EXTRACTED.value
        ):
            self._stage_extract_clips(job, work_dir)
        checkpoint = JobCheckpoint(job.checkpoint)

        if _checkpoint_index(checkpoint.value) < _checkpoint_index(JobCheckpoint.STITCHED.value):
            self._stage_stitch(job, work_dir)
        checkpoint = JobCheckpoint(job.checkpoint)

        if _checkpoint_index(checkpoint.value) < _checkpoint_index(
            JobCheckpoint.AUDIO_ADDED.value
        ):
            self._stage_audio(job, work_dir)

        self.repo.mark_completed(job)

    def _download_inputs(self, job: JobRecord, work_dir: Path) -> dict[str, Path]:
        if self._local_inputs:
            return self._local_inputs

        inputs_dir = work_dir / "inputs"
        inputs_dir.mkdir(exist_ok=True)
        mapping: dict[str, Path] = {}
        for inp in job.inputs:
            local = inputs_dir / inp.filename
            if not local.exists() or local.stat().st_size == 0:
                self.storage.download(inp.storage_key, local)
            mapping[inp.storage_key] = local
        self._local_inputs = mapping
        return mapping

    def _stage_analyze(self, job: JobRecord, work_dir: Path) -> None:
        self.repo.set_checkpoint(job, JobCheckpoint.UPLOADED, 10)
        local_inputs = self._download_inputs(job, work_dir)
        analyze_dir = work_dir / "analyze"
        analyze_dir.mkdir(exist_ok=True)

        # Load CLIP once in the main thread before parallel keyframe analysis
        self.analyzer.ensure_loaded()

        all_candidates = []

        def analyze_one(inp) -> list:
            return self.analyzer.analyze_video(
                local_inputs[inp.storage_key],
                inp.storage_key,
                inp.filename,
                job.prompt,
                analyze_dir,
            )

        with ThreadPoolExecutor(max_workers=settings.parallel_analyze_workers) as pool:
            futures = [pool.submit(analyze_one, inp) for inp in job.inputs]
            for future in as_completed(futures):
                all_candidates.extend(future.result())

        for inp in job.inputs:
            if inp.duration_sec is None:
                inp.duration_sec = probe_duration(local_inputs[inp.storage_key])
                self.repo.session.add(inp)
        self.repo.session.commit()

        self.repo.save_json_field(
            job,
            "analysis_json",
            [asdict(c) for c in all_candidates],
        )
        self.repo.set_checkpoint(job, JobCheckpoint.ANALYZED, 25)

    def _stage_select_clips(self, job: JobRecord) -> None:
        from app.services.clip_analyzer import FrameCandidate

        raw = self.repo.load_json_field(job, "analysis_json") or []
        candidates = [FrameCandidate(**item) for item in raw]
        selected = self.analyzer.select_clips(candidates, job.duration_sec, job.prompt)
        if not selected:
            raise VideoProcessingError("Could not select clips from uploaded videos")
        job.clip_count = len(selected)
        self.repo.save_json_field(job, "selected_clips_json", selected)
        self.repo.set_checkpoint(job, JobCheckpoint.CLIPS_SELECTED, 35)

    def _stage_extract_clips(self, job: JobRecord, work_dir: Path) -> None:
        selected = self.repo.load_json_field(job, "selected_clips_json") or []
        local_inputs = self._download_inputs(job, work_dir)
        from app.services.encode_settings import get_encode_settings

        width, height = get_encode_settings().dimensions(job.orientation)
        clips_dir = work_dir / "clips"
        clips_dir.mkdir(exist_ok=True)

        def extract_one(index: int, clip: dict) -> tuple[int, str]:
            local_clip = clips_dir / f"clip_{index:03d}.mp4"
            if not local_clip.exists():
                extract_clip(
                    local_inputs[clip["storage_key"]],
                    clip["start_sec"],
                    clip["duration_sec"],
                    local_clip,
                    width,
                    height,
                )
            storage_key = f"jobs/{job.id}/clips/{index:03d}.mp4"
            self.storage.upload(local_clip, storage_key, content_type="video/mp4")
            return index, storage_key

        clip_keys: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=settings.parallel_extract_workers) as pool:
            futures = [pool.submit(extract_one, i, c) for i, c in enumerate(selected)]
            done = 0
            for future in as_completed(futures):
                index, key = future.result()
                clip_keys[index] = key
                done += 1
                job.progress = min(35 + int((done / len(selected)) * 35), 70)
                self.repo.update_job(job)

        ordered_keys = [clip_keys[i] for i in sorted(clip_keys.keys())]
        self.repo.save_json_field(job, "extracted_clip_keys_json", ordered_keys)
        self.repo.set_checkpoint(job, JobCheckpoint.CLIPS_EXTRACTED, 70)

    def _local_clips(self, work_dir: Path, clip_keys: list[str]) -> list[Path]:
        clips_dir = work_dir / "clips"
        local = sorted(clips_dir.glob("clip_*.mp4"))
        if len(local) == len(clip_keys):
            return local

        clips_dl = work_dir / "clips_dl"
        clips_dl.mkdir(exist_ok=True)
        paths: list[Path] = []
        for index, key in enumerate(clip_keys):
            path = clips_dl / f"clip_{index:03d}.mp4"
            if not path.exists():
                self.storage.download(key, path)
            paths.append(path)
        return paths

    def _stage_stitch(self, job: JobRecord, work_dir: Path) -> None:
        clip_keys = self.repo.load_json_field(job, "extracted_clip_keys_json") or []
        local_clips = self._local_clips(work_dir, clip_keys)

        stitched = work_dir / "stitched.mp4"
        concat_clips(local_clips, stitched)
        job.output_duration_sec = enforce_max_duration(stitched, settings.max_output_duration_sec)

        storage_key = f"jobs/{job.id}/stitched.mp4"
        self.storage.upload(stitched, storage_key, content_type="video/mp4")
        job.stitched_storage_key = storage_key
        self.repo.set_checkpoint(job, JobCheckpoint.STITCHED, 85)

    def _stage_audio(self, job: JobRecord, work_dir: Path) -> None:
        stitched = work_dir / "stitched.mp4"
        if not stitched.exists():
            self.storage.download(job.stitched_storage_key, stitched)

        duration = job.output_duration_sec or probe_duration(stitched)
        audio_path = work_dir / "audio.m4a"
        self.audio.generate(audio_path, duration, job.prompt)

        final_local = work_dir / "final.mp4"
        mux_audio_video(stitched, audio_path, final_local)

        output_key = f"jobs/{job.id}/final.mp4"
        self.storage.upload(final_local, output_key, content_type="video/mp4")
        job.output_storage_key = output_key
        self.repo.set_checkpoint(job, JobCheckpoint.AUDIO_ADDED, 95)
