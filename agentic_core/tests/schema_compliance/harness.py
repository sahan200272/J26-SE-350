"""Schema-compliance harness (NFR-04). Helper module, not a test.

See docs/evaluation/schema_compliance_definition.md. In short: a case is
compliant when the model's FIRST answer (prefilter off) parses as JSON AND
passes DraftPlan validation. No retry, no repair.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import asdict
from typing import Any, Callable

from pydantic import ValidationError

from agentic_core.decoding.extractor import SYSTEM_PROMPT, extract_plan
from agentic_core.decoding.plan_schema import DraftPlan
from agentic_core.llm.client import LLMResult
from agentic_core.llm.config import load_config
from agentic_core.segmentation.segmenter import segment_transcript
from agentic_core.segmentation.transcript import parse_transcript
from agentic_core.tests.schema_compliance.cases import CATEGORY_COUNTS, recording_date

MODES = ("grammar", "baseline")
TARGET_RATE = 0.98
MAX_ERROR_DETAILS = 10


class RecordingClient:
    """Wraps the real client like a tape recorder: passes calls through and keeps the raw answer.

    In "baseline" mode it sends no grammar (format=None). Nothing else changes.
    """

    def __init__(self, inner: Any, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.inner = inner
        self.config = inner.config  # extract_plan reads config.num_predict
        self.mode = mode
        self.last: LLMResult | None = None
        self.grammar_sent: list[bool] = []

    def chat(self, user_prompt: str, system_prompt: str | None = None,
             response_format: dict | None = None) -> LLMResult:
        sent = response_format if self.mode == "grammar" else None
        self.grammar_sent.append(sent is not None)
        self.last = None
        self.last = self.inner.chat(user_prompt, system_prompt=system_prompt, response_format=sent)
        return self.last


def check_output(text: str) -> tuple[bool, bool, list[str], list[str]]:
    """Return (json_valid, schema_valid, error_types, error_details) for one raw answer."""
    try:
        json.loads(text)
        json_valid = True
    except (json.JSONDecodeError, TypeError):
        json_valid = False
    try:
        DraftPlan.model_validate_json(text)
    except ValidationError as exc:
        errors = exc.errors()
        types = sorted({e["type"] for e in errors})
        details = [f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['type']}" for e in errors]
        return json_valid, False, types, details[:MAX_ERROR_DETAILS]
    return json_valid, True, [], []


def run_case(case: dict, client: RecordingClient) -> dict[str, Any]:
    """Run one case. An exception from the LLM call becomes status 'infra_error'."""
    transcript = parse_transcript(case["transcript"])
    segments = segment_transcript(transcript)
    if len(segments) != 1:
        raise ValueError(f"{case['id']}: expected 1 segment, got {len(segments)}")
    reference = recording_date(transcript.started_at)

    record: dict[str, Any] = {"id": case["id"], "category": case["category"]}
    started = time.perf_counter()
    try:
        result = extract_plan(segments[0], client, reference, use_prefilter=False)
    except Exception as exc:  # Ollama down, timeout, ... : not a model answer
        record.update(status="infra_error", infra_error=f"{type(exc).__name__}: {str(exc)[:200]}",
                      wall_s=round(time.perf_counter() - started, 3))
        return record

    raw = client.last.text if client.last is not None else ""
    json_valid, schema_valid, error_types, error_details = check_output(raw)
    record.update(
        status="ran",
        compliant=schema_valid,
        json_valid=json_valid,
        schema_valid=schema_valid,
        cut_off=result.tokens_out >= client.config.num_predict,
        error_types=error_types,
        error_details=error_details,
        extractor_error=result.error,
        extractor_agrees=(result.plan is not None) == schema_valid,
        tokens_out=result.tokens_out,
        tpot_ms=round(result.tpot_ms, 2),
        llm_total_s=round(result.total_s, 3),
        wall_s=round(time.perf_counter() - started, 3),
        raw_output=raw,
    )
    return record


def run_cases(cases: list[dict], client: RecordingClient,
              on_record: Callable[[int, dict], None] | None = None) -> tuple[list[dict], bool]:
    """Run cases in order. Returns (records, interrupted). Ctrl+C stops early but keeps what ran."""
    records: list[dict] = []
    try:
        for index, case in enumerate(cases, start=1):
            record = run_case(case, client)
            records.append(record)
            if on_record is not None:
                on_record(index, record)
    except KeyboardInterrupt:
        return records, True
    return records, False


def wilson_interval(successes: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion. None when n is 0."""
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _summary_of(records: list[dict]) -> dict[str, Any]:
    ran = [r for r in records if r["status"] == "ran"]
    compliant = sum(r["compliant"] for r in ran)
    interval = wilson_interval(compliant, len(ran))
    return {
        "cases_run": len(ran),
        "infra_errors": sum(r["status"] == "infra_error" for r in records),
        "compliant": compliant,
        "json_valid": sum(r["json_valid"] for r in ran),
        "schema_valid": sum(r["schema_valid"] for r in ran),
        "cut_off": sum(r["cut_off"] for r in ran),
        "extractor_disagrees": sum(not r["extractor_agrees"] for r in ran),
        "rate": compliant / len(ran) if ran else None,
        "ci95_low": interval[0] if interval else None,
        "ci95_high": interval[1] if interval else None,
        "error_type_counts": dict(Counter(t for r in ran for t in r["error_types"])),
        "mean_tokens_out": round(sum(r["tokens_out"] for r in ran) / len(ran), 1) if ran else None,
        "mean_llm_total_s": round(sum(r["llm_total_s"] for r in ran) / len(ran), 2) if ran else None,
    }


def summarize(records: list[dict]) -> dict[str, Any]:
    categories = [c for c in CATEGORY_COUNTS if any(r["category"] == c for r in records)]
    return {
        "total": _summary_of(records),
        "by_category": {c: _summary_of([r for r in records if r["category"] == c]) for c in categories},
    }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def setup_hashes() -> dict[str, str]:
    """Hashes of what must not change after the setup freeze (parsed, so line endings do not matter)."""
    return {
        "system_prompt": _sha(SYSTEM_PROMPT),
        "draft_schema": _sha(json.dumps(DraftPlan.model_json_schema(), sort_keys=True)),
        "llm_config": _sha(json.dumps(asdict(load_config()), sort_keys=True)),
    }
