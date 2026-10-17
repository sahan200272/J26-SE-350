"""Tests for the plan schemas (RP-14, section 5). No LLM is used here."""
import json

import pytest
from pydantic import ValidationError

from agentic_core.decoding.plan_schema import (
    MAX_EVENTS,
    MAX_NOTES,
    MAX_TITLE_CHARS,
    ActionPlan,
    DraftPlan,
)


def note(**overrides):
    item = {"title": "Idea", "body": "Try a cache."}
    item.update(overrides)
    return item


def event(**overrides):
    item = {"title": "Design review", "day": "friday", "time": "15:00"}
    item.update(overrides)
    return item


def test_valid_draft_uses_defaults():
    draft = DraftPlan.model_validate({"notes": [note()], "events": [event()]})
    assert draft.notes[0].folder == "Inbox"
    assert draft.events[0].attendees == []


def test_empty_draft_means_nothing_to_do():
    draft = DraftPlan.model_validate({"notes": [], "events": []})
    assert draft.notes == [] and draft.events == []


@pytest.mark.parametrize("bad_draft", [
    {"notes": [note(body="")], "events": []},                          # empty body
    {"notes": [note(body="   ")], "events": []},                       # body only spaces
    {"notes": [note(title="")], "events": []},                         # empty title
    {"notes": [note(title="x" * (MAX_TITLE_CHARS + 1))], "events": []},  # title too long
    {"notes": [note(folder="../../etc")], "events": []},               # folder not allowed
    {"notes": [note(extra_field="hello")], "events": []},              # unknown field
    {"notes": [], "events": [event(day="Friday")]},                    # capital letter
    {"notes": [], "events": [event(day="next week")]},                 # not a day word
    {"notes": [], "events": [event(time="3 pm")]},                     # not HH:MM
    {"notes": [], "events": [event(time="25:00")]},                    # impossible hour
    {"notes": [], "events": [event(time="9:5")]},                      # not zero padded
    {"notes": [], "events": [event(time="15:00:00")]},                 # seconds not allowed
    {"notes": [], "events": [event(time="")]},                         # empty time
    {"notes": [], "events": [{"title": "x", "day": "friday"}]},        # time missing
    {"notes": [], "events": [event(start="2026-10-16T15:00:00")]},     # old style field
    {"notes": [note()] * (MAX_NOTES + 1), "events": []},               # too many notes
    {"notes": [], "events": [event()] * (MAX_EVENTS + 1)},             # too many events
    {"notes": []},                                                     # events list missing
    {"actions": []},                                                   # old plan shape
])
def test_bad_drafts_are_rejected(bad_draft):
    with pytest.raises(ValidationError):
        DraftPlan.model_validate(bad_draft)


def test_invalid_json_text_is_rejected():
    with pytest.raises(ValidationError):
        DraftPlan.model_validate_json('Sure! Here is your plan: {"notes": [], "events": []}')


def test_schema_sent_to_ollama_has_no_anyof():
    # Design guard: we keep the schema flat because nested "one of" shapes
    # are untested with Ollama.
    assert "anyOf" not in json.dumps(DraftPlan.model_json_schema())


def test_final_plan_takes_a_real_start_time():
    plan = ActionPlan.model_validate(
        {"notes": [], "events": [{"title": "Demo", "start": "2026-10-16T10:00:00"}]}
    )
    assert plan.events[0].start.hour == 10 and plan.is_empty is False


def test_final_plan_rejects_a_day_word_as_start():
    with pytest.raises(ValidationError):
        ActionPlan.model_validate({"notes": [], "events": [{"title": "Demo", "start": "Friday"}]})


def test_empty_final_plan_is_empty():
    assert ActionPlan(notes=[], events=[]).is_empty is True