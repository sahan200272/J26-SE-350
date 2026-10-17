"""Plan schema: the exact shape of what the LLM is allowed to write (RP-14)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_ACTIONS = 5        # untuned guess
MAX_TITLE_CHARS = 80   # untuned guess


class PlannedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["create_note", "create_calendar_event"]
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    folder: Literal["Inbox", "Meetings", "Ideas"] = "Inbox"
    body: str = ""
    start: str = ""
    attendees: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_required_fields(self):
        if self.method == "create_note" and not self.body.strip():
            raise ValueError("create_note needs a non-empty body")
        if self.method == "create_calendar_event":
            try:
                datetime.fromisoformat(self.start)
            except ValueError:
                raise ValueError("create_calendar_event needs start as an ISO 8601 time")
        return self


class ActionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[PlannedAction] = Field(max_length=MAX_ACTIONS)
