"""One-time model setup for the hub, and a record of exactly what is installed.

    # check only (offline; never downloads): verifies the local cache, writes models.lock.json
    python -m hub_speech_pipeline.asr.setup_models --check base small

    # download what is missing (network; only after approval, see CLAUDE.md rule 3)
    python -m hub_speech_pipeline.asr.setup_models --download base

Downloads go to the standard local caches the runtime reads: the Hugging Face hub cache
(``models--Systran--faster-whisper-<size>``, pinned revision, only the files faster-whisper
loads) and the torch hub cache (``checkpoints/<alignment checkpoint>``). No Hugging Face token
is sent (``token=False``).

``hub_speech_pipeline/asr/models.lock.json`` records, for each model, the repository, pinned
revision, file sizes and SHA-256s, plus the versions of the libraries that load them. It holds
no local paths.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path

from . import models

LOCK_FILE = Path(__file__).with_name("models.lock.json")
PACKAGES = ["whisperx", "faster-whisper", "ctranslate2", "torch", "torchaudio", "pyannote.audio",
            "transformers", "huggingface-hub"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(model: str, language: str = "en") -> None:
    spec = models.WHISPER_MODELS[model]
    snapshot = models.whisper_snapshot(spec)
    if not models.missing_files(model, language) and snapshot.is_dir():
        print(f"{model}: already in the cache, nothing to download")
        return
    from huggingface_hub import snapshot_download

    print(f"downloading {spec.repo_id}@{spec.revision} ({spec.total_bytes / 1e6:.1f} MB) ...", flush=True)
    snapshot_download(spec.repo_id, revision=spec.revision, allow_patterns=list(spec.files),
                      cache_dir=str(models.hf_hub_cache()), token=False)
    # faster-whisper loads "main": point refs/main at the pinned revision.
    ref = snapshot.parent.parent / "refs" / "main"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(spec.revision)

    align = models.ALIGN_MODELS[language]
    checkpoint = models.align_checkpoint(align)
    if not checkpoint.is_file():
        import torch.hub

        print(f"downloading {align.url} ({align.size / 1e6:.1f} MB) ...", flush=True)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        torch.hub.download_url_to_file(align.url, str(checkpoint), progress=False)


def lock_record(selected: list[str], language: str = "en") -> dict:
    record = {
        "recorded_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "packages": {p: importlib.metadata.version(p) for p in PACKAGES},
        "whisper_models": {},
        "alignment_models": {},
        "vad": "whisperx bundled pyannote segmentation (whisperx/assets/pytorch_model.bin)",
    }
    for name in selected:
        spec = models.WHISPER_MODELS[name]
        snapshot = models.whisper_snapshot(spec)
        record["whisper_models"][name] = {
            "repo_id": spec.repo_id, "revision": spec.revision, "license": spec.license,
            "files": {f: {"bytes": (snapshot / f).stat().st_size, "sha256": sha256(snapshot / f)}
                      for f in spec.files},
        }
    align = models.ALIGN_MODELS[language]
    checkpoint = models.align_checkpoint(align)
    record["alignment_models"][language] = {
        "torchaudio_bundle": align.bundle, "file": align.file, "url": align.url,
        "bytes": checkpoint.stat().st_size, "sha256": sha256(checkpoint),
    }
    vad = Path(importlib.util.find_spec("whisperx").origin).parent / "assets" / "pytorch_model.bin"
    record["vad_sha256"] = sha256(vad) if vad.is_file() else None
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", nargs="+", metavar="MODEL", choices=sorted(models.WHISPER_MODELS))
    mode.add_argument("--download", nargs="+", metavar="MODEL", choices=sorted(models.WHISPER_MODELS))
    args = parser.parse_args(argv)
    selected = args.check or args.download

    if args.download:
        for name in selected:
            download(name)
    problems = {name: models.missing_files(name) for name in selected}
    for name, missing in problems.items():
        print(f"{name}: " + ("OK (all files present, sizes match)" if not missing else "MISSING"))
        for m in missing:
            print(f"   - {m}")
    if any(problems.values()):
        print("not recording models.lock.json: some models are missing")
        return 1
    LOCK_FILE.write_text(json.dumps(lock_record(selected), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {LOCK_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
