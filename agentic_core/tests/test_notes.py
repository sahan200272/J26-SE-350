"""Tests for note writing (RP-16, section 2a)."""

from datetime import date

import pytest

from agentic_core.mcp_servers.filesystem_server import notes
from agentic_core.mcp_servers.filesystem_server.notes import (
    NoteError,
    make_slug,
    write_note,
)
from agentic_core.mcp_servers.filesystem_server.sandbox import (
    SandboxConfig,
    SandboxViolation,
)

DAY = date(2026, 10, 18)


@pytest.fixture()
def config(tmp_path):
    return SandboxConfig(vault_root=tmp_path / "vault")


@pytest.mark.parametrize(
    "title, slug",
    [
        ("Budget Review: Q3!", "budget-review-q3"),
        ("../../etc/passwd", "etc-passwd"),
        ("  --  ", "untitled"),
        ("", "untitled"),
        ("NUL", "nul"),
        ("සිංහල රැස්වීම", "සිංහල-රැස්වීම"),
        ("a" * 200, "a" * 60),
    ],
)
def test_make_slug(title, slug):
    assert make_slug(title) == slug


def test_writes_note_with_code_built_name(config):
    rel = write_note(config, "Ideas", "Budget Review", "Hello", today=DAY)
    assert rel == "Ideas/2026-10-18_budget-review.md"
    written = (config.vault_root / rel).read_bytes()
    assert written == b"Hello\n"


def test_crlf_is_turned_into_lf(config):
    rel = write_note(config, "Inbox", "x", "a\r\nb", today=DAY)
    assert (config.vault_root / rel).read_bytes() == b"a\nb\n"


def test_same_title_never_overwrites(config):
    first = write_note(config, "Inbox", "Plan", "one", today=DAY)
    second = write_note(config, "Inbox", "Plan", "two", today=DAY)
    assert second == "Inbox/2026-10-18_plan-2.md"
    assert (config.vault_root / first).read_bytes() == b"one\n"
    assert (config.vault_root / second).read_bytes() == b"two\n"


def test_evil_title_cannot_change_the_path(config):
    rel = write_note(config, "Inbox", "../../etc/passwd", "x", today=DAY)
    assert rel == "Inbox/2026-10-18_etc-passwd.md"


def test_bad_folder_is_blocked_by_the_guard(config):
    with pytest.raises(SandboxViolation) as info:
        write_note(config, "../outside", "x", "y", today=DAY)
    assert info.value.reason == "TRAVERSAL"
    with pytest.raises(SandboxViolation) as info:
        write_note(config, "Secrets", "x", "y", today=DAY)
    assert info.value.reason == "NOT_ALLOWED_DIR"


def test_creates_the_zone_folder_if_missing(config):
    assert not config.vault_root.exists()
    write_note(config, "Meetings", "x", "y", today=DAY)
    assert (config.vault_root / "Meetings").is_dir()


def test_sinhala_title_works_on_disk(config):
    rel = write_note(config, "Ideas", "සිංහල රැස්වීම", "ok", today=DAY)
    assert (config.vault_root / rel).exists()


@pytest.mark.parametrize(
    "content, reason",
    [
        ("", "EMPTY_CONTENT"),
        ("   \n", "EMPTY_CONTENT"),
        (None, "EMPTY_CONTENT"),
                pytest.param("x" * (notes.MAX_CONTENT_CHARS + 1), "CONTENT_TOO_LARGE", id="too-large"),
        ("bad \ud800 surrogate", "BAD_ENCODING"),
    ],
)
def test_bad_content_is_rejected_and_leaves_no_file(config, content, reason):
    with pytest.raises(NoteError) as info:
        write_note(config, "Inbox", "x", content, today=DAY)
    assert info.value.reason == reason
    assert not any(config.vault_root.rglob("*.md"))


def test_non_text_title_is_rejected(config):
    with pytest.raises(NoteError) as info:
        write_note(config, "Inbox", None, "y", today=DAY)
    assert info.value.reason == "BAD_TITLE"


def test_too_many_duplicates(config, monkeypatch):
    monkeypatch.setattr(notes, "MAX_DUPLICATES", 2)
    for _ in range(3):  # base name, -2, -3
        write_note(config, "Inbox", "x", "y", today=DAY)
    with pytest.raises(NoteError) as info:
        write_note(config, "Inbox", "x", "y", today=DAY)
    assert info.value.reason == "TOO_MANY_DUPLICATES"