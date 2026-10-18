"""WhisperX on CPU: models loaded once, then one call per chunk.

Offline: :func:`enforce_offline` runs before whisperx (and with it faster-whisper,
huggingface_hub and pyannote) is imported, and the models are checked in the local cache first;
a missing model raises :class:`ModelMissingError` instead of downloading.
"""

from __future__ import annotations

import importlib.metadata
import time
from pathlib import Path

from hub_speech_pipeline.common.offline import blocked_attempts, enforce_offline

from . import models


class WhisperXEngine:
    def __init__(self, model: str = "base", compute_type: str = "int8", language: str = "en",
                 threads: int = 4, batch_size: int = 8):
        self.offline_env = enforce_offline()
        models.require_models(model, language)
        import whisperx  # after enforce_offline()

        self._whisperx = whisperx
        self.language = language
        self.batch_size = batch_size
        start = time.perf_counter()
        self.model = whisperx.load_model(model, device="cpu", compute_type=compute_type,
                                         language=language, threads=threads, local_files_only=True)
        self.align_model, self.align_metadata = whisperx.load_align_model(language, "cpu")
        self.load_s = time.perf_counter() - start
        spec = models.WHISPER_MODELS[model]
        align = models.ALIGN_MODELS[language]
        self.info = {
            "whisper_model": model,
            "repo_id": spec.repo_id,
            "revision": spec.revision,
            "compute_type": compute_type,
            "device": "cpu",
            "threads": threads,
            "batch_size": batch_size,
            "language": language,
            "align_model": align.bundle,
            "vad": "pyannote (whisperx bundled)",
            "whisperx": importlib.metadata.version("whisperx"),
            "faster_whisper": importlib.metadata.version("faster-whisper"),
            "ctranslate2": importlib.metadata.version("ctranslate2"),
            "torch": importlib.metadata.version("torch"),
        }

    def transcribe(self, audio_path: Path) -> tuple[list[dict], dict]:
        """(aligned segments with words, stage timings in ms incl. decoded duration)."""
        wx = self._whisperx
        t0 = time.perf_counter()
        audio = wx.load_audio(str(audio_path))
        t1 = time.perf_counter()
        result = self.model.transcribe(audio, batch_size=self.batch_size, language=self.language)
        t2 = time.perf_counter()
        segments = result.get("segments", [])
        if segments:
            aligned = wx.align(segments, self.align_model, self.align_metadata, audio, "cpu",
                               return_char_alignments=False)
            segments = aligned.get("segments", [])
        t3 = time.perf_counter()
        return segments, {
            "decode_ms": round((t1 - t0) * 1000, 1),
            "transcribe_ms": round((t2 - t1) * 1000, 1),
            "align_ms": round((t3 - t2) * 1000, 1),
            "decoded_duration_s": round(len(audio) / 16000, 4),
        }

    @staticmethod
    def network_attempts() -> list[str]:
        return blocked_attempts()
