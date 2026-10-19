"""Settings for the calendar MCP server (RP-16, section 3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")

# Untuned guesses.
DURATION_RANGE = (5, 1440)  # minutes
REMINDER_RANGE = (0, 1440)  # minutes


class ConfigError(Exception):
    """The settings file is wrong. The message says what to fix."""


@dataclass(frozen=True)
class CalendarConfig:
    time_zone: str = "Asia/Colombo"
    default_duration_minutes: int = 60
    default_reminder_minutes: int = 10

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.time_zone)


def _check_int(name: str, value: object, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ConfigError(f"{name} must be a whole number from {low} to {high}")
    return value


def load_config(path: Path | None = None) -> CalendarConfig:
    """Read and check the settings file. Unknown keys are an error (catches typos)."""
    source = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"cannot read settings file: {source.name}") from error
    if not isinstance(raw, dict):
        raise ConfigError("settings file must be a list of 'name: value' lines")

    defaults = CalendarConfig()
    unknown = set(raw) - set(defaults.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"unknown setting(s): {', '.join(sorted(map(str, unknown)))}")

    time_zone = raw.get("time_zone", defaults.time_zone)
    try:
        if not isinstance(time_zone, str):
            raise ValueError
        ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(
            f"unknown time zone {time_zone!r} (on Windows: pip install tzdata)"
        ) from None

    return CalendarConfig(
        time_zone=time_zone,
        default_duration_minutes=_check_int(
            "default_duration_minutes",
            raw.get("default_duration_minutes", defaults.default_duration_minutes),
            *DURATION_RANGE,
        ),
        default_reminder_minutes=_check_int(
            "default_reminder_minutes",
            raw.get("default_reminder_minutes", defaults.default_reminder_minutes),
            *REMINDER_RANGE,
        ),
    )