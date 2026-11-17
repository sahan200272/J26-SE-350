"""Tests for the compaction rules (RP-18, section 3). Synthetic vaults only."""

from agentic_core.compaction.collect import collect
from agentic_core.compaction.config import CompactionConfig
from agentic_core.compaction.rules import build_digest, normalize

from .helpers import NOW, add_event, add_note, make_vault

CONFIG = CompactionConfig()


def digest_of(vault):
    result = collect(vault, CONFIG, NOW)
    return build_digest(list(result.notes), CONFIG, NOW, result.skipped)


def test_normalize_ignores_case_spaces_and_punctuation():
    assert normalize("  Send the BUDGET, please! ") == "send the budget please"
    assert normalize("කසුන්ට  කතා කරන්න") == "කසුන්ට කතා කරන්න"


def test_checkbox_lines_become_tasks_and_inbox_notes_become_reminders(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Meetings/a.md", "Budget", "We agreed.\n- [ ] Send figures\n* [ ] Book room", "2026-11-17T10:00")
    add_note(vault, "Inbox/b.md", "Call the bank", "about the loan", "2026-11-17T11:00")
    add_note(vault, "Ideas/c.md", "New logo", "maybe blue", "2026-11-17T12:00")  # an idea, not a task

    digest = digest_of(vault)
    assert sorted(t.text for t in digest.open_tasks) == ["Book room", "Call the bank", "Send figures"]
    assert len(digest.new_notes) == 3


def test_same_task_in_two_sessions_is_one_task(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Meetings/a.md", "Mon", "- [ ] Send the budget", "2026-11-16T10:00", plan="p1")
    add_note(vault, "Meetings/b.md", "Tue", "- [ ] send the budget.", "2026-11-17T10:00", plan="p2")

    (task,) = digest_of(vault).open_tasks
    assert task.mentions == 2 and len(task.sources) == 2
    assert task.priority == 2 and "mentioned 2 times" in task.reasons


def test_latest_mention_wins_for_done_and_reopened(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Inbox/a.md", "x", "- [ ] Pay rent\n- [ ] Fix laptop", "2026-11-16T09:00")
    add_note(vault, "Inbox/b.md", "y", "- [x] Pay rent\n- [x] Fix laptop", "2026-11-17T09:00")
    add_note(vault, "Inbox/c.md", "z", "- [ ] Fix laptop", "2026-11-17T15:00")  # broke again

    digest = digest_of(vault)
    assert [t.text for t in digest.done_today] == ["Pay rent"]
    assert [t.key for t in digest.open_tasks] == ["fix laptop"]


def test_task_done_long_ago_is_not_in_done_today(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Inbox/a.md", "x", "- [x] Old thing", "2026-11-10T09:00")
    digest = digest_of(vault)
    assert digest.done_today == [] and digest.open_tasks == []


def test_task_matching_a_synced_event_counts_as_scheduled(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Inbox/a.md", "Book budget review with Alice", "", "2026-11-17T10:00", plan="p1")
    add_event(vault, "Meetings/e.md", "Budget review", "2026-11-19T10:00", "2026-11-17T10:01", plan="p9")

    digest = digest_of(vault)
    assert digest.open_tasks == []
    (task,) = digest.scheduled_tasks
    assert task.event.title == "Budget review"


def test_task_linked_to_an_event_that_is_not_synced_stays_open(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Meetings/a.md", "Plan", "- [ ] Prepare slides", "2026-11-17T10:00", plan="p1")
    add_event(vault, "Meetings/e.md", "Demo", "2026-11-18T09:00", "2026-11-17T10:00", synced=False, plan="p1")

    digest = digest_of(vault)
    (task,) = digest.open_tasks
    assert task.event.title == "Demo"  # linked through the plan id
    assert task.priority == 1 and "meeting Wed 09:00" in task.reasons
    assert [e.title for e in digest.unsynced_events] == ["Demo"]


def test_urgent_words_and_carried_over_tasks(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Inbox/a.md", "x", "- [ ] Submit report ASAP", "2026-11-17T09:00")
    add_note(vault, "Inbox/b.md", "y", "- [ ] Clean desk", "2026-11-12T09:00")
    add_note(vault, "Inbox/c.md", "z", "- [ ] Water plants", "2026-11-16T09:00")

    tasks = {t.key: t for t in digest_of(vault).open_tasks}
    assert tasks["submit report asap"].priority == 1
    assert tasks["clean desk"].priority == 2 and "carried over 5 day(s)" in tasks["clean desk"].reasons
    assert tasks["water plants"].priority == 3 and "carried over 1 day(s)" in tasks["water plants"].reasons


def test_rerun_copies_of_one_event_are_merged(tmp_path):
    vault = make_vault(tmp_path)
    add_event(vault, "Meetings/e.md", "Review", "2026-11-18T09:00", "2026-11-17T10:00", synced=False)
    add_event(vault, "Meetings/e-2.md", "Review", "2026-11-18T09:00", "2026-11-17T11:00", synced=True)

    (event,) = digest_of(vault).events
    assert event.synced is True and len(event.notes) == 2


def test_open_tasks_are_sorted_by_priority_then_age(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Inbox/a.md", "x", "- [ ] B later", "2026-11-17T08:00")
    add_note(vault, "Inbox/b.md", "y", "- [ ] A urgent", "2026-11-17T09:00")
    add_note(vault, "Inbox/c.md", "z", "- [ ] C later", "2026-11-17T07:00")

    assert [t.text for t in digest_of(vault).open_tasks] == ["A urgent", "C later", "B later"]


def test_plan_link_to_a_synced_event_does_not_count_as_handled(tmp_path):
    vault = make_vault(tmp_path)
    add_note(vault, "Meetings/a.md", "Plan", "- [ ] Prepare slides", "2026-11-17T10:00", plan="p1")
    add_event(vault, "Meetings/e.md", "Demo", "2026-11-18T09:00", "2026-11-17T10:00", synced=True, plan="p1")

    digest = digest_of(vault)
    assert digest.scheduled_tasks == []
    (task,) = digest.open_tasks
    assert task.matched_by == "plan" and task.priority == 1
