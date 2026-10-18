"""Calendar logic for the calendar MCP server (RP-16, section 3a).

Checks the input, builds the event in the configured time zone and writes it
through a backend. No MCP and no LLM here. The backend is a plug: a fake
in-memory calendar for tests, a Google one later.

Attendees are NAMES, not email addresses. They go into the description.
No invitation is ever sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from .config import DURATION_RANGE, REMINDER_RANGE, CalendarConfig

# Untuned guesses.
MAX_TITLE_CHARS = 200
MAX_ATTENDEES = 20
MAX_ATTENDEE_CHARS = 100


class CalendarError(Exception):
    """An event was refused. The message is only a reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BackendError(Exception):
    """The calendar backend failed (network, login, ...). The message is only a reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class NewEvent:
    title: str
    start: datetime  # always has a time zone
    end: datetime
    description: str
    reminder_minutes: int


@dataclass(frozen=True)
class StoredEvent:
    event_id: str
    title: str
    start: datetime
    end: datetime
    reminder_minutes: int
    description: str


@dataclass(frozen=True)
class CreateResult:
    status: str  # "created" or "exists"
    event: StoredEvent


class CalendarBackend(Protocol):
    def find(self, title: str, start: datetime) -> StoredEvent | None:
        """Return an event with the same title and the same start, if any."""
        ...

    def add(self, event: NewEvent) -> StoredEvent:
        """Store a new event and return it with its id."""
        ...


def title_key(title: str) -> str:
    """Same-title test: ignore case and extra spaces."""
    return " ".join(title.split()).casefold()


class InMemoryCalendar:
    """A fake calendar for tests. Nothing leaves the computer."""

    def __init__(self) -> None:
        self.events: list[StoredEvent] = []

    def find(self, title: str, start: datetime) -> StoredEvent | None:
        for event in self.events:
            if title_key(event.title) == title_key(title) and event.start == start:
                return event
        return None

    def add(self, event: NewEvent) -> StoredEvent:
        stored = StoredEvent(
            event_id=f"mem-{len(self.events) + 1}",
            title=event.title,
            start=event.start,
            end=event.end,
            reminder_minutes=event.reminder_minutes,
            description=event.description,
        )
        self.events.append(stored)
        return stored


def _has_control_chars(text: str) -> bool:
    return any(ord(ch) < 32 for ch in text)


def _check_title(title: object) -> str:
    if not isinstance(title, str) or not title.strip() or _has_control_chars(title):
        raise CalendarError("BAD_TITLE")
    clean = " ".join(title.split())
    if len(clean) > MAX_TITLE_CHARS:
        raise CalendarError("TITLE_TOO_LONG")
    return clean


def _check_start(start: object, config: CalendarConfig) -> datetime:
    if not isinstance(start, str):
        raise CalendarError("BAD_START")
    try:
        parsed = datetime.fromisoformat(start)
    except ValueError:
        raise CalendarError("BAD_START") from None
    if parsed.tzinfo is not None:  # plans hold local time; the config decides the zone
        raise CalendarError("TIMEZONE_NOT_ALLOWED")
    return parsed.replace(tzinfo=config.zone)


def _check_minutes(value: object, default: int, bounds: tuple[int, int], reason: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalendarError(reason)
    if not bounds[0] <= value <= bounds[1]:
        raise CalendarError(reason)
    return value


def _check_attendees(attendees: object) -> list[str]:
    if attendees is None:
        return []
    if not isinstance(attendees, list):
        raise CalendarError("BAD_ATTENDEE")
    if len(attendees) > MAX_ATTENDEES:
        raise CalendarError("TOO_MANY_ATTENDEES")
    names: list[str] = []
    for name in attendees:
        if (
            not isinstance(name, str)
            or not name.strip()
            or _has_control_chars(name)
            or len(name) > MAX_ATTENDEE_CHARS
        ):
            raise CalendarError("BAD_ATTENDEE")
        names.append(" ".join(name.split()))
    return names


def create_event(
    backend: CalendarBackend,
    config: CalendarConfig,
    *,
    title: object,
    start: object,
    attendees: object = None,
    duration_minutes: object = None,
    reminder_minutes: object = None,
) -> CreateResult:
    """Create one event, or return the existing one. Raises CalendarError."""
    clean_title = _check_title(title)
    start_at = _check_start(start, config)
    names = _check_attendees(attendees)
    duration = _check_minutes(
        duration_minutes, config.default_duration_minutes, DURATION_RANGE, "BAD_DURATION"
    )
    reminder = _check_minutes(
        reminder_minutes, config.default_reminder_minutes, REMINDER_RANGE, "BAD_REMINDER"
    )

    existing = backend.find(clean_title, start_at)
    if existing is not None:
        return CreateResult("exists", existing)

    description = f"Attendees: {', '.join(names)}" if names else ""
    stored = backend.add(
        NewEvent(
            title=clean_title,
            start=start_at,
            end=start_at + timedelta(minutes=duration),
            description=description,
            reminder_minutes=reminder,
        )
    )
    return CreateResult("created", stored)