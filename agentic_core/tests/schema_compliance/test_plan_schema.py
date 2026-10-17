"""Tests for the plan schema (RP-14, section 2). No LLM is used here."""
import json

import pytest
from pydantic import ValidationError

from agentic_core.decoding.plan_schema import MAX_ACTIONS, MAX_TITLE_CHARS, ActionPlan


def note(**overrides):
    action = {"method": "create_note", "title": "Idea", "body": "Try a cache."}
    action.update(overrides)
    return action


def event(**overrides):
    action = {"method": "create_calendar_event", "title": "Design review",
              "start": "2026-10-23T15:00:00"}
    action.update(overrides)
    return action


def test_valid_calendar_plan():
    plan = ActionPlan.model_validate({"actions": [event()]})
    assert plan.actions[0].method == "create_calendar_event"


def test_valid_note_uses_default_folder():
    plan = ActionPlan.model_validate({"actions": [note()]})
    assert plan.actions[0].folder == "Inbox"


def test_empty_plan_means_no_action():
    assert ActionPlan.model_validate({"actions": []}).actions == []


@pytest.mark.parametrize("bad_plan", [
    {"actions": [note(method="delete_file")]},                  # unknown tool
    {"actions": [note(body="")]},                               # note without body
    {"actions": [note(body="   ")]},                            # body only spaces
    {"actions": [event(start="Friday")]},                       # not an ISO time
    {"actions": [event(start="")]},                             # missing time
    {"actions": [note(folder="../../etc")]},                    # folder not allowed
    {"actions": [note(title="")]},                              # empty title
    {"actions": [note(title="x" * (MAX_TITLE_CHARS + 1))]},     # title too long
    {"actions": [note(extra_field="hello")]},                   # unknown field
    {"actions": [note()] * (MAX_ACTIONS + 1)},                  # too many actions
    {"steps": []},                                              # wrong top-level name
])
def test_bad_plans_are_rejected(bad_plan):
    with pytest.raises(ValidationError):
        ActionPlan.model_validate(bad_plan)


def test_invalid_json_text_is_rejected():
    with pytest.raises(ValidationError):
        ActionPlan.model_validate_json('Sure! Here is your plan: {"actions": []}')


def test_schema_has_no_anyof():
    # Design guard: we keep the schema flat because nested "one of" shapes
    # are untested with Ollama.
    assert "anyOf" not in json.dumps(ActionPlan.model_json_schema())
