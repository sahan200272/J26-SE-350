"""Settings for the nightly compaction job (RP-18, section 3).

Read from config.yaml next to this file. Unknown or badly typed settings
stop the job with a clear message instead of running with a wrong value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

_RUN_TIME = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


@dataclass(frozen=True)
class CompactionConfig:
    time_zone: str = "Asia/Colombo"
    run_time: str = "20:00"
    window_hours: int = 24
    lookback_days: int = 14
    stale_after_days: int = 3
    upcoming_days: int = 7
    max_items_per_section: int = 15
    summary_chars: int = 160
    max_note_chars: int = 100_000
    urgent_words: tuple[str, ...] = (
        "urgent", "asap", "today", "tonight", "deadline", "eod", "immediately",
    )

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.time_zone)


def load_config(path: Path = CONFIG_PATH) -> CompactionConfig:
    """Read the settings. Raises ValueError for unknown or bad values."""
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected 'name: value' lines")

    allowed = {field.name: field for field in fields(CompactionConfig)}
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ValueError(f"{path}: unknown setting(s): {', '.join(unknown)}")

    values: dict = {}
    for name, value in data.items():
        if name in ("time_zone", "run_time"):
            if not isinstance(value, str):
                raise ValueError(f"{path}: '{name}' must be text, got {value!r}")
        elif name == "urgent_words":
            if not isinstance(value, list) or not all(isinstance(w, str) and w for w in value):
                raise ValueError(f"{path}: 'urgent_words' must be a list of words")
            value = tuple(w.casefold() for w in value)
        elif isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{path}: '{name}' must be a whole number >= 1, got {value!r}")
        values[name] = value

    config = CompactionConfig(**values)
    if not _RUN_TIME.fullmatch(config.run_time):
        raise ValueError(f"{path}: 'run_time' must look like HH:MM (24-hour)")
    try:
        config.zone
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"{path}: unknown time zone {config.time_zone!r}") from None
    return config
