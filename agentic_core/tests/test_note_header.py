"""Tests for the YAML note header (RP-18, section 2)."""

import pytest

from agentic_core.mcp_servers import note_header


def test_render_then_split_gives_the_same_fields_back():
    fields = {
        "type": "event",
        "created": "2026-11-17T10:42:00+05:30",
        "plan": "20261117-104200-3f2a",
        "start": "2026-11-18T09:30",
        "attendees": ["Alice", "Kasun"],
        "synced_to_calendar": True,
    }
    text = note_header.render(fields) + "# Title\n\nBody\n"
    header, rest = note_header.split(text)
    assert header == fields
    assert rest == "# Title\n\nBody\n"


def test_dates_and_words_stay_text_not_other_types():
    header, _ = note_header.split(note_header.render({"created": "2026-11-17", "x": "true"}))
    assert header == {"created": "2026-11-17", "x": "true"}


def test_windows_line_endings_are_fine():
    text = (note_header.render({"type": "note"}) + "# T\n").replace("\n", "\r\n")
    header, rest = note_header.split(text)
    assert header == {"type": "note"} and rest == "# T\n"


def test_sinhala_and_tamil_text_is_kept():
    header, _ = note_header.split(note_header.render({"attendees": ["කසුන්", "தமிழ்"]}))
    assert header["attendees"] == ["කසුන්", "தமிழ்"]


@pytest.mark.parametrize(
    "text",
    [
        "# No header\n",
        "---\ntype: note\n# never closed\n",
        "---\n: : bad yaml [\n---\nbody\n",
        "---\n- a list\n---\nbody\n",
        "",
    ],
    ids=["none", "not-closed", "bad-yaml", "not-a-mapping", "empty"],
)
def test_missing_or_broken_header_gives_none_and_never_raises(text):
    header, rest = note_header.split(text)
    assert header is None
    assert rest == text
