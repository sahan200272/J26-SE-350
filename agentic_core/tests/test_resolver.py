"""Tests for the resolver: day words to dates, duplicates, attendees (RP-14, section 5)."""
from datetime import date, datetime

import pytest

from agentic_core.decoding.plan_schema import DraftEvent, DraftPlan, PlannedNote
from agentic_core.decoding.resolver import resolve_day, resolve_plan

MONDAY = date(2026, 10, 12)
FRIDAY_MONTH_END = date(2026, 10, 30)


@pytest.mark.parametrize("day, expected", [
    ("today", date(2026, 10, 12)),
    ("tomorrow", date(2026, 10, 13)),
    ("thursday", date(2026, 10, 15)),
    ("friday", date(2026, 10, 16)),
    ("sunday", date(2026, 10, 18)),
    ("monday", date(2026, 10, 19)),   # same weekday means next week
])
def test_days_counted_from_a_monday(day, expected):
    assert resolve_day(day, MONDAY) == expected


@pytest.mark.parametrize("day, expected", [
    ("tomorrow", date(2026, 10, 31)),
    ("tuesday", date(2026, 11, 3)),   # crosses into the next month
])
def test_days_cross_the_month_end(day, expected):
    assert resolve_day(day, FRIDAY_MONTH_END) == expected


def draft_event(**overrides):
    item = {"title": "Demo", "day": "friday", "time": "10:00", "attendees": []}
    item.update(overrides)
    return DraftEvent(**item)


def make_draft(notes=(), events=()):
    return DraftPlan(notes=list(notes), events=list(events))


def test_event_gets_a_real_start_time():
    plan = resolve_plan(make_draft(events=[draft_event()]), MONDAY)
    assert plan.events[0].start == datetime(2026, 10, 16, 10, 0)


def test_empty_draft_gives_empty_plan():
    assert resolve_plan(make_draft(), MONDAY).is_empty is True


def test_duplicate_notes_are_removed_ignoring_case_and_spaces():
    first = PlannedNote(title="Review login bug", body="Review it after the call")
    again = PlannedNote(title="review  LOGIN bug", body="review it after   the call")
    plan = resolve_plan(make_draft(notes=[first, again]), MONDAY)
    assert plan.notes == [first]


def test_notes_with_different_text_are_both_kept_in_order():
    one = PlannedNote(title="A", body="first")
    two = PlannedNote(title="A", body="second")
    plan = resolve_plan(make_draft(notes=[one, two]), MONDAY)
    assert plan.notes == [one, two]


def test_duplicate_events_are_removed_but_a_different_time_is_kept():
    events = [draft_event(), draft_event(), draft_event(time="11:00")]
    plan = resolve_plan(make_draft(events=events), MONDAY)
    assert [e.start.hour for e in plan.events] == [10, 11]


def test_speaker_labels_are_not_attendees():
    event = draft_event(attendees=["Speaker 1", "speaker 2", "Kasun", "kasun", " Nimal  Perera "])
    plan = resolve_plan(make_draft(events=[event]), MONDAY)
    assert plan.events[0].attendees == ["Kasun", "Nimal Perera"]