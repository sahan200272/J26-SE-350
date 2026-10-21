"""Loader for the schema-compliance case files (NFR-04).

Helper module, not a test. The fingerprint lets a test notice if anyone edits
the 200 evaluation cases after they were frozen.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parents[2] / "datasets" / "schema_compliance"
EVAL_PATH = DATASET_DIR / "eval_cases.json"
DEV_PATH = DATASET_DIR / "dev_cases.json"

CATEGORY_COUNTS = {"single_intent": 50, "multi_intent": 75, "noise": 50, "ambiguous": 25}


def load_cases(path: Path = EVAL_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def fingerprint(cases: list[dict]) -> str:
    """SHA-256 of the cases in a canonical form (ignores spaces and line endings in the file)."""
    canonical = json.dumps(cases, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def recording_date(started_at: str) -> date:
    """The day of the recording, from the transcript header."""
    return datetime.fromisoformat(started_at).date()
