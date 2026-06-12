import logging
import subprocess
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class AudioGenerator:
    """Generate production-ready synthetic audio using Hugging Face MusicGen or FFmpeg fallback."""

    def generate(self, output_path: Path, duration_sec: float, prompt: str | None) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if settings.enable_musicgen:
            try:
                self._generate_musicgen(output_path, duration_sec, prompt)
                return
            except Exception as exc:
                logger.warning("MusicGen failed, using FFmpeg fallback: %s", exc)
        self._generate_ffmpeg_ambient(output_path, duration_sec, prompt)

    def _generate_musicgen(self, output_path: Path, duration_sec: float, prompt: str | None) -> None:
        import scipy.io.wavfile
        import torch
        from transformers import MusicgenForConditionalGeneration, AutoProcessor

        logger.info("Loading MusicGen: %s", settings.musicgen_model_id)
        processor = AutoProcessor.from_pretrained(
            settings.musicgen_model_id, cache_dir=str(settings.hf_cache_dir)
        )
        model = MusicgenForConditionalGeneration.from_pretrained(
            settings.musicgen_model_id, cache_dir=str(settings.hf_cache_dir)
        )
        model.eval()

        text = prompt or "upbeat cinematic background music, instrumental, no vocals"
        text = f"{text}, background music for video, professional production quality"

        max_tokens = min(int(duration_sec * 50), 512)
        inputs = processor(text=[text], padding=True, return_tensors="pt")
        with torch.no_grad():
            audio = model.generate(**inputs, max_new_tokens=max_tokens)

        wav_path = output_path.with_suffix(".wav")
        sampling_rate = model.config.audio_encoder.sampling_rate
        scipy.io.wavfile.write(wav_path, rate=sampling_rate, data=audio[0, 0].numpy())

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(wav_path),
                "-t",
                str(duration_sec),
                "-af",
                "loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.5,afade=t=out:st="
                f"{max(0, duration_sec - 0.5)}:d=0.5",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
        wav_path.unlink(missing_ok=True)

    def _generate_ffmpeg_ambient(self, output_path: Path, duration_sec: float, prompt: str | None) -> None:
        # Layered synthetic bed — normalized and faded for production feel
        freq = "220" if prompt and "calm" in prompt.lower() else "330"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={freq}:duration={duration_sec}",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:duration={duration_sec}",
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=longest,volume=0.25,"
                "loudnorm=I=-14:TP=-1.5:LRA=11,"
                f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, duration_sec - 0.5)}:d=0.5",
                "-t",
                str(duration_sec),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )


_audio_generator: AudioGenerator | None = None


def get_audio_generator() -> AudioGenerator:
    global _audio_generator
    if _audio_generator is None:
        _audio_generator = AudioGenerator()
    return _audio_generator
