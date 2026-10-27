"""The standard Whisper English text normaliser, used for every WER in the project (from E0).

The code is transformers' ``EnglishTextNormalizer`` (a copy of OpenAI Whisper's
``whisper/normalizers/english.py``); its spelling table is OpenAI's ``english.json`` at a pinned
commit, kept next to this module with its SHA-256 (see ``whisper_normalizer/NOTICE.md``).

The normaliser lowercases, removes text in brackets and filler words (hmm, mm, mhm, mmm, uh,
um), expands contractions and titles (mr -> mister), converts spelled-out numbers to digits
("twentieth" -> "20th", "ten" -> "10"), standardises British spellings, and removes
punctuation and symbols.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.metadata
import json
from pathlib import Path

SPELLING_FILE = Path(__file__).with_name("whisper_normalizer") / "english.json"
SPELLING_SHA256 = "6607f948be9824d2e1b2fa2223cd94c06c45afa4e05ea0e3d5e1f2bdffde2465"
SPELLING_COMMIT = "ea1c266709125f68a89acdc0c6ddbde6773eb0ed"


@functools.lru_cache(maxsize=1)
def _normalizer():
    data = SPELLING_FILE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SPELLING_SHA256:
        raise RuntimeError(f"{SPELLING_FILE} has SHA-256 {digest}, expected {SPELLING_SHA256}")
    from transformers.models.whisper.english_normalizer import EnglishTextNormalizer

    return EnglishTextNormalizer(json.loads(data))


def whisper_normalize(text: str) -> str:
    return _normalizer()(text)


def provenance() -> dict:
    """What a WER computed with this normaliser depends on (for reports)."""
    return {
        "normaliser": "Whisper EnglishTextNormalizer (transformers copy of openai/whisper normalizers/english.py)",
        "transformers": importlib.metadata.version("transformers"),
        "spelling_table": "openai/whisper whisper/normalizers/english.json",
        "spelling_table_commit": SPELLING_COMMIT,
        "spelling_table_sha256": SPELLING_SHA256,
    }
