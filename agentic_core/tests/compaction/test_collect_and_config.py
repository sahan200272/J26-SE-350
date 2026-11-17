"""Tests for reading the vault and the settings (RP-18, section 3)."""

import os

import pytest

from agentic_core.compaction.collect import collect
from agentic_core.compaction.config import CompactionConfig, load_config

from .helpers import NOW, add_event, add_note, add_plain, make_vault

CONFIG = CompactionConfig()


def test_shipped_config_file_loads():
    config = load_config()
    assert config.run_time == "20:00" and config.window_hours == 24
    assert "urgent" in config.urgent_words


@pytest.mark.parametrize(
    "text",
    [
        "window_hours: 0\n",
        "window_hours: yes\n",
        "colour: blue\n",
        "run_time: '8pm'\n",
        "time_zone: Mars/Base\n",
        "urgent_words: urgent\n",
        "- a list\n",
    ],
    ids=["zero", "bool", "unknown", "bad-time", "bad-zone", "words-not-list", "not-mapping"],
)
def test_bad_settings_are_refused(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_collect_reads_headers_titles_and_kinds(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Meetings/2026-11-17_budget.md", "Budget", "- [ ] send figures", "2026-11-17T10:00")
    add_event(
        vault, "Meetings/2026-11-17_review.md", "Review", "2026-11-18T09:30",
        "2026-11-17T10:00", attendees=("Alice",),
    )
    add_plain(vault, "Ideas/my idea.md", "Just a thought\n", "2026-11-17T12:00")

    result = collect(vault, CONFIG, NOW)
    by_path = {n.path: n for n in result.notes}
    budget = by_path["Meetings/2026-11-17_budget.md"]
    assert (budget.kind, budget.title, budget.body, budget.plan) == (
        "note", "Budget", "- [ ] send figures", "p1",
    )
    review = by_path["Meetings/2026-11-17_review.md"]
    assert review.kind == "event" and review.synced is True and review.attendees == ("Alice",)
    assert review.start.isoformat() == "2026-11-18T09:30:00+05:30"
    plain = by_path["Ideas/my idea.md"]
    assert (plain.kind, plain.title, plain.created.hour) == ("plain", "my idea", 12)
    assert plain.link == "[[Ideas/my idea]]"


def test_old_large_and_non_markdown_files_are_skipped(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Inbox/old.md", "Old", "x", "2026-10-01T10:00")
    (vault / "Inbox" / "big.md").write_text("x" * (CONFIG.max_note_chars + 1), encoding="utf-8")
    (vault / "Inbox" / "photo.png").write_bytes(b"\x89PNG")
    (vault / "todo.md").write_text("old digest", encoding="utf-8")  # root files are not input

    result = collect(vault, CONFIG, NOW)
    assert result.notes == ()
    assert result.skipped == {"TOO_OLD": 1, "TOO_LARGE": 1}


def test_a_shortcut_out_of_the_vault_is_never_read(tmp_path):
    vault = make_vault(tmp_path)
    secret = tmp_path / "secret.md"
    secret.write_text("# SECRET\n\n- [ ] SECRET task\n", encoding="utf-8")
    try:
        os.symlink(secret, vault / "Inbox" / "link.md")
    except OSError:
        pytest.skip("this machine cannot make symlinks")
    result = collect(vault, CONFIG, NOW)
    assert result.notes == ()
    assert result.skipped == {"BLOCKED": 1}


def test_a_broken_header_does_not_stop_the_job(tmp_path):
    vault = make_vault(tmp_path)
    add_plain(vault, "Inbox/broken.md", "---\n: : [\n---\n# Call Nimal\n", "2026-11-17T09:00")
    (note,) = collect(vault, CONFIG, NOW).notes
    assert note.kind == "plain"
