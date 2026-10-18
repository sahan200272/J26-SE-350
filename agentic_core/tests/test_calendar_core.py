"""Tests for the calendar settings and core logic (RP-16, section 3a)."""

from datetime import timedelta

import pytest

from agentic_core.mcp_servers.calendar_server.config import (
    CalendarConfig,
    ConfigError,
    load_config,
)
from agentic_core.mcp_servers.calendar_server.core import (
    InMemoryCalendar,
    CalendarError,
    create_event,
)

START = "2026-10-19T15:00"


@pytest.fixture()
def calendar():
    return InMemoryCalendar()


@pytest.fixture()
def config():
    return CalendarConfig()


# ---------- settings ----------


def test_default_settings_file_is_valid():
    cfg = load_config()
    assert cfg.time_zone == "Asia/Colombo"
    assert cfg.default_duration_minutes == 60
    assert cfg.default_reminder_minutes == 10


def write_settings(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "text",
    [
        "time_zone: Mars/Olympus\n",
        "time_zone: 5\n",
        "default_duration_minutes: 0\n",
        "default_duration_minutes: true\n",
        "default_reminder_minutes: -1\n",
        "default_reminder_minutes: ten\n",
        "time_zon: Asia/Colombo\n",  # typo in the name
        "- just\n- a list\n",
        "",
    ],
)
def test_bad_settings_are_refused(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(write_settings(tmp_path, text))


def test_missing_settings_file_is_refused(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_partial_settings_use_defaults(tmp_path):
    cfg = load_config(write_settings(tmp_path, "default_reminder_minutes: 30\n"))
    assert cfg.default_reminder_minutes == 30
    assert cfg.time_zone == "Asia/Colombo"


# ---------- creating events ----------


def test_event_gets_colombo_time_zone_and_defaults(calendar, config):
    result = create_event(calendar, config, title="Budget review", start=START)
    event = result.event
    assert result.status == "created"
    assert event.start.utcoffset() == timedelta(hours=5, minutes=30)
    assert event.start.replace(tzinfo=None).isoformat() == "2026-10-19T15:00:00"
    assert event.end - event.start == timedelta(minutes=60)
    assert event.reminder_minutes == 10
    assert event.description == ""


def test_explicit_duration_and_reminder(calendar, config):
    event = create_event(
        calendar, config, title="x", start=START, duration_minutes=45, reminder_minutes=0
    ).event
    assert event.end - event.start == timedelta(minutes=45)
    assert event.reminder_minutes == 0


def test_attendee_names_go_into_the_description_only(calendar, config):
    event = create_event(
        calendar, config, title="Sync", start=START, attendees=["Alice", " Bob  Silva "]
    ).event
    assert event.description == "Attendees: Alice, Bob Silva"


def test_same_title_and_start_is_not_created_twice(calendar, config):
    first = create_event(calendar, config, title="Budget review", start=START)
    again = create_event(calendar, config, title="  budget   REVIEW ", start=START)
    assert again.status == "exists"
    assert again.event.event_id == first.event.event_id
    assert len(calendar.events) == 1


def test_same_title_other_time_is_a_new_event(calendar, config):
    create_event(calendar, config, title="Standup", start=START)
    other = create_event(calendar, config, title="Standup", start="2026-10-20T09:30")
    assert other.status == "created"
    assert len(calendar.events) == 2


def test_title_is_cleaned(calendar, config):
    event = create_event(calendar, config, title="  Plan   launch ", start=START).event
    assert event.title == "Plan launch"


def test_other_time_zone_setting_is_used(calendar):
    cfg = CalendarConfig(time_zone="UTC")
    event = create_event(calendar, cfg, title="x", start=START).event
    assert event.start.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"title": "", "start": START}, "BAD_TITLE"),
        ({"title": "   ", "start": START}, "BAD_TITLE"),
        ({"title": "a\nb", "start": START}, "BAD_TITLE"),
        ({"title": None, "start": START}, "BAD_TITLE"),
        ({"title": "a" * 201, "start": START}, "TITLE_TOO_LONG"),
        ({"title": "x", "start": "tomorrow"}, "BAD_START"),
        ({"title": "x", "start": ""}, "BAD_START"),
        ({"title": "x", "start": 5}, "BAD_START"),
        ({"title": "x", "start": "2026-10-19T15:00:00+00:00"}, "TIMEZONE_NOT_ALLOWED"),
        ({"title": "x", "start": "2026-10-19T15:00:00Z"}, "TIMEZONE_NOT_ALLOWED"),
        ({"title": "x", "start": START, "duration_minutes": 0}, "BAD_DURATION"),
        ({"title": "x", "start": START, "duration_minutes": 1441}, "BAD_DURATION"),
        ({"title": "x", "start": START, "duration_minutes": True}, "BAD_DURATION"),
        ({"title": "x", "start": START, "duration_minutes": "60"}, "BAD_DURATION"),
        ({"title": "x", "start": START, "reminder_minutes": -1}, "BAD_REMINDER"),
        ({"title": "x", "start": START, "reminder_minutes": 1.5}, "BAD_REMINDER"),
        ({"title": "x", "start": START, "attendees": "Alice"}, "BAD_ATTENDEE"),
        ({"title": "x", "start": START, "attendees": [""]}, "BAD_ATTENDEE"),
        ({"title": "x", "start": START, "attendees": [5]}, "BAD_ATTENDEE"),
        ({"title": "x", "start": START, "attendees": ["a\nb"]}, "BAD_ATTENDEE"),
        ({"title": "x", "start": START, "attendees": ["n" * 101]}, "BAD_ATTENDEE"),
        ({"title": "x", "start": START, "attendees": ["p"] * 21}, "TOO_MANY_ATTENDEES"),
    ],
)
def test_bad_input_is_refused_and_nothing_is_stored(calendar, config, kwargs, reason):
    with pytest.raises(CalendarError) as info:
        create_event(calendar, config, **kwargs)
    assert info.value.reason == reason
    assert str(info.value) == reason
    assert calendar.events == []