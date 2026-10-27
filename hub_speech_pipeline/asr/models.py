"""The models the hub uses, pinned, and the offline availability check.

Whisper models are CTranslate2 conversions loaded by faster-whisper (as WhisperX does) from the
Hugging Face cache; the English alignment model is torchaudio's ``WAV2VEC2_ASR_BASE_960H``,
loaded by WhisperX from the torch hub cache. WhisperX's VAD weights ship inside the whisperx
package (``whisperx/assets/pytorch_model.bin``) and need no download.

Sizes and revisions were taken from the Hugging Face API and download.pytorch.org on
2026-10-18 (see hub_speech_pipeline/test_output/H1_report.md).
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class WhisperModelSpec:
    name: str  # WhisperX / faster-whisper model size, e.g. "base"
    repo_id: str
    revision: str  # pinned Hugging Face commit
    files: dict[str, int]  # file name -> size in bytes (the files faster-whisper loads)
    license: str = "MIT"

    @property
    def total_bytes(self) -> int:
        return sum(self.files.values())


@dataclasses.dataclass(frozen=True)
class AlignModelSpec:
    language: str
    bundle: str  # torchaudio.pipelines name
    file: str  # checkpoint file in <torch hub>/checkpoints/
    url: str
    size: int


WHISPER_MODELS = {
    "base": WhisperModelSpec(
        "base", "Systran/faster-whisper-base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
        {"config.json": 2309, "model.bin": 145217532, "tokenizer.json": 2203239, "vocabulary.txt": 459861},
    ),
    "small": WhisperModelSpec(
        "small", "Systran/faster-whisper-small", "536b0662742c02347bc0e980a01041f333bce120",
        {"config.json": 2370, "model.bin": 483546902, "tokenizer.json": 2203239, "vocabulary.txt": 459861},
    ),
}

ALIGN_MODELS = {
    "en": AlignModelSpec(
        "en", "WAV2VEC2_ASR_BASE_960H", "wav2vec2_fairseq_base_ls960_asr_ls960.pth",
        "https://download.pytorch.org/torchaudio/models/wav2vec2_fairseq_base_ls960_asr_ls960.pth",
        377664473,
    ),
}


class ModelMissingError(RuntimeError):
    """A required model is not in the local cache (the hub never downloads at run time)."""


def hf_hub_cache() -> Path:
    """The Hugging Face hub cache faster-whisper reads (honours HF_HUB_CACHE / HF_HOME)."""
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    home = os.environ.get("HF_HOME") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache"), "huggingface")
    return Path(home) / "hub"


def torch_hub_dir() -> Path:
    """The torch hub directory WhisperX's alignment loader reads (honours TORCH_HOME)."""
    if os.environ.get("TORCH_HOME"):
        return Path(os.environ["TORCH_HOME"]) / "hub"
    return Path(os.environ.get("XDG_CACHE_HOME") or os.path.join(Path.home(), ".cache")) / "torch" / "hub"


def whisper_snapshot(spec: WhisperModelSpec, cache: Path | None = None) -> Path:
    cache = cache or hf_hub_cache()
    return cache / f"models--{spec.repo_id.replace('/', '--')}" / "snapshots" / spec.revision


def align_checkpoint(spec: AlignModelSpec, hub_dir: Path | None = None) -> Path:
    return (hub_dir or torch_hub_dir()) / "checkpoints" / spec.file


def missing_files(model: str, language: str = "en", hf_cache: Path | None = None,
                  hub_dir: Path | None = None) -> list[str]:
    """Human-readable list of what is missing for ``model`` + the ``language`` aligner."""
    if model not in WHISPER_MODELS:
        raise ValueError(f"unknown model {model!r}; known: {sorted(WHISPER_MODELS)}")
    missing = []
    spec = WHISPER_MODELS[model]
    snapshot = whisper_snapshot(spec, hf_cache)
    for name, size in spec.files.items():
        path = snapshot / name
        if not path.is_file():
            missing.append(f"{spec.repo_id}@{spec.revision[:8]}: {name} (expected at {path})")
        elif size is not None and path.stat().st_size != size:
            missing.append(f"{spec.repo_id}@{spec.revision[:8]}: {name} has {path.stat().st_size} B, expected {size} B")
    # faster-whisper resolves "main" through refs/main, which must point at the pinned revision.
    ref = snapshot.parent.parent / "refs" / "main"
    if snapshot.is_dir() and (not ref.is_file() or ref.read_text().strip() != spec.revision):
        missing.append(f"{spec.repo_id}: refs/main does not point at the pinned revision {spec.revision[:8]}")
    align = ALIGN_MODELS[language]
    checkpoint = align_checkpoint(align, hub_dir)
    if not checkpoint.is_file():
        missing.append(f"alignment {align.bundle}: {align.file} (expected at {checkpoint})")
    elif checkpoint.stat().st_size != align.size:
        missing.append(f"alignment {align.bundle}: {align.file} has {checkpoint.stat().st_size} B, expected {align.size} B")
    return missing


def require_models(model: str, language: str = "en", **kwargs) -> None:
    """Raises :class:`ModelMissingError` naming every missing file and the setup command."""
    missing = missing_files(model, language, **kwargs)
    if missing:
        raise ModelMissingError(
            f"model '{model}' cannot run offline; missing from the local cache:\n  - "
            + "\n  - ".join(missing)
            + f"\nDownload once (needs network and approval):"
            f"\n  python -m hub_speech_pipeline.asr.setup_models --download {model}"
        )
