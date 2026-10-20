"""Status logic for the PP1 panel dashboard.

Rule: a row is MET only when a real number was read from a result file
and that number meets the target. Everything that is missing, unreadable,
null or marked as not valid is NOT MEASURED. Never a pass by default.
"""

from __future__ import annotations

import json
import math
import operator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MET = "MET"
NOT_MET = "NOT MET"
NOT_MEASURED = "NOT MEASURED"

_COMPARE: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
}


@dataclass(frozen=True)
class Reading:
    """What an extractor found in a result file."""

    value: float | None  # in the same unit as the target; None = no usable number
    shown: str  # the measured value as text for the panel
    machine: str = "unknown"
    date: str = "unknown"
    not_valid: str | None = None  # reason the number does not count for this target
    file_limits: tuple[str, ...] = ()  # limits written inside the result file


@dataclass(frozen=True)
class Objective:
    key: str
    name: str
    op: str  # one of _COMPARE
    target: float
    unit: str
    evidence: str | None  # file name inside the evaluation folder; None = no file yet
    extract: Callable[[dict[str, Any]], Reading] | None
    limits: tuple[str, ...] = field(default=())

    @property
    def target_text(self) -> str:
        symbol = "=" if self.op == "==" else self.op
        return f"{symbol} {self.target:g} {self.unit}".strip()


def _row(objective: Objective, status: str, reason: str, reading: Reading | None) -> dict[str, Any]:
    limits = list(objective.limits)
    if reading is not None:
        limits = list(reading.file_limits) + limits
    return {
        "key": objective.key,
        "name": objective.name,
        "target": objective.target_text,
        "status": status,
        "reason": reason,
        "measured": reading.shown if reading else "-",
        "machine": reading.machine if reading else "-",
        "date": reading.date if reading else "-",
        "evidence": objective.evidence or "-",
        "limits": limits,
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def evaluate(objective: Objective, eval_dir: Path) -> dict[str, Any]:
    """Read the evidence file for one objective and decide its status."""
    if objective.evidence is None or objective.extract is None:
        return _row(objective, NOT_MEASURED, "No result file for this objective yet.", None)

    path = eval_dir / objective.evidence
    if not path.is_file():
        return _row(objective, NOT_MEASURED, f"Result file not found: {objective.evidence}", None)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _row(objective, NOT_MEASURED, "Result file could not be read as JSON.", None)
    if not isinstance(data, dict):
        return _row(objective, NOT_MEASURED, "Result file has an unexpected shape.", None)

    try:
        reading = objective.extract(data)
    except (KeyError, TypeError, ValueError, AttributeError):
        return _row(objective, NOT_MEASURED, "Result file is missing a needed field.", None)

    if reading.not_valid is not None:
        return _row(objective, NOT_MEASURED, reading.not_valid, reading)
    if not _is_number(reading.value):
        return _row(objective, NOT_MEASURED, "No usable number in the result file.", reading)

    compare = _COMPARE[objective.op]
    if compare(float(reading.value), objective.target):
        return _row(objective, MET, "Measured value meets the target.", reading)
    return _row(objective, NOT_MET, "Measured value misses the target.", reading)


def evaluate_all(objectives: list[Objective], eval_dir: Path) -> list[dict[str, Any]]:
    return [evaluate(objective, eval_dir) for objective in objectives]
