"""Turn the LLM's draft into the final plan (RP-14, section 5). No LLM here.

An 8B model is weak at calendar maths, so our code does it:
  - day words become real dates,
  - exact duplicates are removed,
  - fake attendees such as "Speaker 1" are dropped.
"""

import re
from datetime import date, datetime, time, timedelta

from agentic_core.decoding.plan_schema import (
    ActionPlan,
    DraftPlan,
    PlannedEvent,
)

_WEEKDAY_NUMBER = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_SPEAKER_LABEL = re.compile(r"speaker\s*\d+", re.IGNORECASE)


def resolve_day(day: str, reference: date) -> date:
    """Turn a day word into a date, counted from the recording date.

    A weekday name means its NEXT turn. If the recording day has the same
    name, that means one week later, because people say "today" for today.
    This rule is an untuned guess.
    """
    if day == "today":
        return reference
    if day == "tomorrow":
        return reference + timedelta(days=1)
    days_ahead = (_WEEKDAY_NUMBER[day] - reference.weekday()) % 7 or 7
    return reference + timedelta(days=days_ahead)


def _same(text: str) -> str:
    """Lower-case text with single spaces, so near-identical text compares equal."""
    return " ".join(text.lower().split())


def _clean_attendees(names: list[str]) -> list[str]:
    kept: list[str] = []
    for name in names:
        name = " ".join(name.split())
        if not name or _SPEAKER_LABEL.fullmatch(name):
            continue
        if _same(name) not in [_same(existing) for existing in kept]:
            kept.append(name)
    return kept


def resolve_plan(draft: DraftPlan, reference: date) -> ActionPlan:
    """Build the final plan from the LLM draft. Order is kept."""
    notes = []
    seen_notes = set()
    for note in draft.notes:
        key = (_same(note.title), _same(note.body))
        if key not in seen_notes:
            seen_notes.add(key)
            notes.append(note)

    events = []
    seen_events = set()
    for event in draft.events:
        start = datetime.combine(
            resolve_day(event.day, reference), time.fromisoformat(event.time)
        )
        key = (_same(event.title), start)
        if key not in seen_events:
            seen_events.add(key)
            events.append(
                PlannedEvent(
                    title=event.title,
                    start=start,
                    attendees=_clean_attendees(event.attendees),
                )
            )

    return ActionPlan(notes=notes, events=events)