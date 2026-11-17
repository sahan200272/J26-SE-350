"""Tests for the two output files and the entry point (RP-18, section 3)."""

from agentic_core.compaction import run as run_module
from agentic_core.compaction.config import CompactionConfig
from agentic_core.compaction.run import compact, main
from agentic_core.mcp_servers.filesystem_server.sandbox import SandboxConfig
from agentic_core.mcp_servers.filesystem_server.server import create_server

from .helpers import NOW, add_event, add_note, make_vault

CONFIG = CompactionConfig()
NOW_ARG = ["--now", "2026-11-17T20:00"]


def busy_vault(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Meetings/2026-11-17_budget.md", "Budget",
             "We cut travel costs.\n- [ ] Send figures to Alice\n- [x] Book room", "2026-11-17T10:00")
    add_event(vault, "Meetings/2026-11-17_review.md", "Review", "2026-11-18T09:30",
              "2026-11-17T10:00", attendees=("Alice", "Kasun"))
    add_event(vault, "Meetings/2026-11-17_demo.md", "Demo day", "2026-11-20T14:00",
              "2026-11-17T10:00", synced=False, plan="p2")
    add_note(vault, "Inbox/2026-11-17_call-bank.md", "Call the bank", "about the loan", "2026-11-17T11:00", plan="p3")
    add_note(vault, "Ideas/2026-11-17_logo.md", "New logo", "Maybe blue.", "2026-11-17T12:00", plan="p4")
    add_note(vault, "Inbox/2026-11-12_desk.md", "Desk", "- [ ] Clean desk", "2026-11-12T09:00", plan="p0")
    return vault


def test_todo_has_the_right_sections_in_order(tmp_path):
    _, todo, _ = compact(busy_vault(tmp_path), CONFIG, NOW)
    order = [line for line in todo.split("\n") if line.startswith("#")]
    assert order == [
        "# To-do: Tuesday 17 November 2026",
        "## Add to your calendar by hand",
        "## Do first (priority 1)",
        "## Soon (priority 2)",
        "## Later (priority 3)",
        f"## In your calendar (next {CONFIG.upcoming_days} days)",
    ]
    assert "- [ ] Demo day, Fri 20 Nov 14:00 — [[Meetings/2026-11-17_demo]]" in todo
    assert "Send figures to Alice _(meeting Wed 09:30)_ — [[Meetings/2026-11-17_budget]]" in todo
    assert "- [ ] Clean desk _(carried over 5 day(s))_" in todo
    assert "- Wed 18 Nov 09:30: Review with Alice, Kasun" in todo
    assert "Book room" not in todo  # done tasks are not in the to-do list


def test_brief_counts_and_lists(tmp_path):
    _, _, brief = compact(busy_vault(tmp_path), CONFIG, NOW)
    assert brief.startswith("# Daily brief: Tuesday 17 November 2026\n")
    assert "_Covers Mon 16 Nov 20:00 to Tue 17 Nov 20:00." in brief
    assert "- 3 new note(s), 2 meeting(s) planned today" in brief
    assert "- 3 open task(s): 1 to do first, 1 carried over from earlier days" in brief
    assert "**1 meeting(s) are NOT in your calendar yet**" in brief
    assert "- **New logo**: Maybe blue. — [[Ideas/2026-11-17_logo]]" in brief
    assert "- [x] Book room — [[Meetings/2026-11-17_budget]]" in brief
    assert "0 handled by a calendar event" in brief  # a plan link alone is not "handled"
    assert "- Demo day: Fri 20 Nov 14:00 (NOT in calendar)" in brief


def test_empty_vault_still_gives_two_friendly_files(tmp_path):
    _, todo, brief = compact(make_vault(tmp_path), CONFIG, NOW)
    assert "Nothing open. Enjoy your evening." in todo
    assert "- 0 new note(s), 0 meeting(s) planned today" in brief


def test_note_text_cannot_add_headings_or_fake_links(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Inbox/x.md", "Evil", "- [ ] pay [[../../secret]] now\n## Fake heading", "2026-11-17T10:00")
    _, todo, brief = compact(vault, CONFIG, NOW)
    assert "[[../../secret]]" not in todo + brief
    assert "## Fake heading" not in todo + brief


def test_long_sections_are_capped(tmp_path):
    vault = make_vault(tmp_path)
    body = "\n".join(f"- [ ] task number {i}" for i in range(40))
    add_note(vault, "Inbox/many.md", "Many", body, "2026-11-17T10:00")
    _, todo, _ = compact(vault, CONFIG, NOW)
    assert f"- … and {40 - CONFIG.max_items_per_section} more" in todo


def test_same_vault_same_time_gives_the_same_files(tmp_path):
    vault = busy_vault(tmp_path)
    assert compact(vault, CONFIG, NOW)[1:] == compact(vault, CONFIG, NOW)[1:]


# ---------- the entry point ----------


def test_main_writes_both_files_through_mcp_and_nothing_else(tmp_path):
    vault = busy_vault(tmp_path)
    before = sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*"))
    server = create_server(SandboxConfig(vault_root=vault))

    assert main(["--vault", str(vault), *NOW_ARG], target=server) == 0
    after = sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*"))
    assert sorted(set(after) - set(before)) == ["daily_brief.md", "todo.md"]
    assert (vault / "todo.md").read_text(encoding="utf-8").startswith("# To-do: Tuesday")

    # second run overwrites, never adds -2 copies
    assert main(["--vault", str(vault), *NOW_ARG], target=server) == 0
    assert sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*")) == after


def test_dry_run_prints_and_writes_nothing(tmp_path, capsys):
    vault = busy_vault(tmp_path)
    assert main(["--vault", str(vault), "--dry-run", *NOW_ARG]) == 0
    out = capsys.readouterr().out
    assert "===== todo.md =====" in out and "===== daily_brief.md =====" in out
    assert not (vault / "todo.md").exists()


def test_bad_input_gives_exit_code_2(tmp_path):
    assert main(["--vault", str(tmp_path / "missing")]) == 2
    bad = tmp_path / "bad.yaml"
    bad.write_text("window_hours: 0\n", encoding="utf-8")
    assert main(["--vault", str(make_vault(tmp_path)), "--config", str(bad)]) == 2


def test_a_refused_write_gives_exit_code_1(tmp_path, monkeypatch):
    vault = make_vault(tmp_path)
    monkeypatch.setattr(run_module, "TODO_NAME", "evil.md")  # not on the allowlist
    server = create_server(SandboxConfig(vault_root=vault))
    assert main(["--vault", str(vault), *NOW_ARG], target=server) == 1
    assert not (vault / "evil.md").exists()
    assert (vault / "daily_brief.md").exists()  # one failure does not stop the other file


def test_log_never_holds_note_text(tmp_path, caplog):
    vault = make_vault(tmp_path)
    add_note(vault, "Inbox/x.md", "SECRET title", "- [ ] SECRET task", "2026-11-17T10:00")
    server = create_server(SandboxConfig(vault_root=vault))
    with caplog.at_level("INFO"):
        assert main(["--vault", str(vault), *NOW_ARG], target=server) == 0
    assert "SECRET" not in caplog.text


def test_real_stdio_server_end_to_end(tmp_path):
    vault = busy_vault(tmp_path)
    assert main(["--vault", str(vault), *NOW_ARG]) == 0  # starts the real server process
    assert (vault / "todo.md").exists() and (vault / "daily_brief.md").exists()
