"""Plan schemas (RP-14, section 5).

Two layers:
  PlannedNote, DraftEvent, DraftPlan
      What the LLM is allowed to write. Small and flat. Ollama's grammar
      enforces this shape.
  PlannedEvent, ActionPlan
      What the rest of the system receives. Our code builds it from the
      draft (see resolver.py), so dates are real dates and nothing is guessed.
"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_NOTES = 5  # untuned guess
MAX_EVENTS = 5  # untuned guess
MAX_TITLE_CHARS = 80  # untuned guess

DayWord = Literal[
    "today", "tomorrow",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
]
Folder = Literal["Inbox", "Meetings", "Ideas"]

_TIME_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class PlannedNote(BaseModel):
    """A note to save. The same shape is used in the draft and in the final plan."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    body: str = Field(min_length=1)
    folder: Folder = "Inbox"

    @field_validator("title", "body")
    @classmethod
    def check_not_blank(cls, value: str) -> str:
        return _not_blank(value)


class DraftEvent(BaseModel):
    """An event as the LLM writes it: a day word and a time, but no real date."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    day: DayWord
    time: str  # 24-hour HH:MM. Checked here in Python, not by the grammar.
    attendees: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def check_title_not_blank(cls, value: str) -> str:
        return _not_blank(value)

    @field_validator("time")
    @classmethod
    def check_time_format(cls, value: str) -> str:
        if not _TIME_PATTERN.fullmatch(value):
            raise ValueError("time must look like HH:MM (24-hour)")
        return value


class PlannedEvent(BaseModel):
    """An event in the final plan: a real start time (local, no time zone yet)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    start: datetime
    attendees: list[str] = Field(default_factory=list)


class DraftPlan(BaseModel):
    """The only shape the LLM may produce. This is the schema sent to Ollama."""

    model_config = ConfigDict(extra="forbid")

    notes: list[PlannedNote] = Field(max_length=MAX_NOTES)
    events: list[DraftEvent] = Field(max_length=MAX_EVENTS)


class ActionPlan(BaseModel):
    """The final plan. Two empty lists mean: nothing to do."""

    model_config = ConfigDict(extra="forbid")

    notes: list[PlannedNote]
    events: list[PlannedEvent]

    @property
    def is_empty(self) -> bool:
        return not self.notes and not self.events