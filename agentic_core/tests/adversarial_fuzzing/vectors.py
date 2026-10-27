"""Loader for the frozen path-traversal vector dataset (RP-16, section 4c).

Helper module, not a test. The fingerprint lets a test notice if anyone edits
the vectors after they were frozen.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "path_traversal_vectors.json"


def load_vectors(path: Path = DATASET_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["vectors"]


def fingerprint(vectors: list[dict]) -> str:
    """SHA-256 of the vectors in a canonical form (ignores spaces and line endings)."""
    canonical = json.dumps(vectors, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()