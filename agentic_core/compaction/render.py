"""Turn a Digest into todo.md and daily_brief.md (RP-18, section 3). No LLM.

Plain Markdown that any editor can open (NFR-06). Each line links back to
its source note with an Obsidian [[link]], so the user can check it.
Text from notes is cut to one line, so a note can never add headings or
break the layout of these two files.
"""

from __future__ import annotations

from datetime import timedelta

from .collect import VaultNote
from .config import CompactionConfig
from .rules import Digest, Event, Task, one_line

_PRIORITY_TITLES = {1: "Do first", 2: "Soon", 3: "Later"}
_NOTICE = (
    "_Made by the nightly compaction job at {time}. This file is replaced every night: "
    "tick tasks in their source notes, not here._"
)


def _clean(text: str, limit: int) -> str:
    # one line only, and no "[[" / "]]" so note text cannot fake a link
    return one_line(text, limit).replace("[[", "[ [").replace("]]", "] ]")


def _when(event: Event) -> str:
    return f"{event.start:%a %d %b %H:%M}" if event.start else "time unknown"


def _links(notes: list[VaultNote], limit: int = 3) -> str:
    links = [n.link for n in notes[:limit]]
    more = len(notes) - limit
    return " · ".join(links) + (f" (+{more})" if more > 0 else "")


def _task_line(task: Task, config: CompactionConfig, done: bool = False) -> str:
    box = "[x]" if done else "[ ]"
    line = f"- {box} {_clean(task.text, config.summary_chars)}"
    if task.reasons and not done:
        line += f" _({'; '.join(task.reasons)})_"
    return f"{line} — {_links(task.sources)}"


def _capped(lines: list[str], total: int, config: CompactionConfig) -> list[str]:
    cap = config.max_items_per_section
    if total > cap:
        return lines[:cap] + [f"- … and {total - cap} more"]
    return lines


def render_todo(digest: Digest, config: CompactionConfig) -> str:
    now = digest.now
    out = [f"# To-do: {now:%A %d %B %Y}", "", _NOTICE.format(time=f"{now:%H:%M}"), ""]

    unsynced = [e for e in digest.unsynced_events if e.start is None or e.start >= now]
    if unsynced:
        out += ["## Add to your calendar by hand", ""]
        lines = [
            f"- [ ] {_clean(e.title, config.summary_chars)}, {_when(e)} — {_links(e.notes)}"
            for e in unsynced
        ]
        out += _capped(lines, len(lines), config) + [""]

    for priority in (1, 2, 3):
        tasks = [t for t in digest.open_tasks if t.priority == priority]
        if not tasks:
            continue
        out += [f"## {_PRIORITY_TITLES[priority]} (priority {priority})", ""]
        lines = [_task_line(t, config) for t in tasks]
        out += _capped(lines, len(lines), config) + [""]

    horizon = now + timedelta(days=config.upcoming_days)
    upcoming = [e for e in digest.events if e.synced and e.start and now <= e.start <= horizon]
    if upcoming:
        out += [f"## In your calendar (next {config.upcoming_days} days)", ""]
        lines = []
        for event in upcoming:
            who = f" with {', '.join(event.attendees)}" if event.attendees else ""
            lines.append(f"- {_when(event)}: {_clean(event.title, config.summary_chars)}{who}")
        out += _capped(lines, len(lines), config) + [""]

    if not unsynced and not digest.open_tasks:
        out += ["Nothing open. Enjoy your evening.", ""]
    return "\n".join(out)


def _first_line(note: VaultNote, config: CompactionConfig) -> str:
    for line in note.body.split("\n"):
        text = line.strip().lstrip("-*+ ").strip()
        if text and not text.startswith("[") and not text.startswith("#"):
            return _clean(text, config.summary_chars)
    return ""


def render_brief(digest: Digest, config: CompactionConfig) -> str:
    now, start = digest.now, digest.window_start
    window_events = [e for e in digest.events if e.created >= start]
    carried = [t for t in digest.open_tasks if t.first_seen < start]
    urgent = [t for t in digest.open_tasks if t.priority == 1]
    unsynced = [e for e in digest.unsynced_events if e.start is None or e.start >= now]

    out = [
        f"# Daily brief: {now:%A %d %B %Y}",
        "",
        f"_Covers {start:%a %d %b %H:%M} to {now:%a %d %b %H:%M}. "
        + _NOTICE.format(time=f"{now:%H:%M}")[1:],
        "",
        "## At a glance",
        "",
        f"- {len(digest.new_notes)} new note(s), {len(window_events)} meeting(s) planned today",
        f"- {len(digest.open_tasks)} open task(s): {len(urgent)} to do first, "
        f"{len(carried)} carried over from earlier days",
        f"- {len(digest.done_today)} task(s) done today, "
        f"{len(digest.scheduled_tasks)} handled by a calendar event",
    ]
    if unsynced:
        out.append(f"- **{len(unsynced)} meeting(s) are NOT in your calendar yet** (see todo.md)")
    if digest.skipped:
        codes = ", ".join(f"{k} {v}" for k, v in sorted(digest.skipped.items()))
        out.append(f"- Files skipped: {codes}")
    out.append("")

    if window_events:
        out += ["## Meetings planned today", ""]
        lines = []
        for event in window_events:
            flag = "in calendar" if event.synced else "NOT in calendar"
            lines.append(
                f"- {_clean(event.title, config.summary_chars)}: {_when(event)} ({flag})"
                f" — {_links(event.notes)}"
            )
        out += _capped(lines, len(lines), config) + [""]

    by_folder: dict[str, list[VaultNote]] = {}
    for note in digest.new_notes:
        by_folder.setdefault(note.folder, []).append(note)
    titles = {"Meetings": "From meetings", "Ideas": "Ideas", "Inbox": "Inbox"}
    for folder in ("Meetings", "Ideas", "Inbox"):
        notes = by_folder.get(folder)
        if not notes:
            continue
        out += [f"## {titles[folder]}", ""]
        lines = []
        for note in notes:
            summary = _first_line(note, config)
            text = f"- **{_clean(note.title, 80)}**"
            text += f": {summary}" if summary else ""
            lines.append(f"{text} — {note.link}")
        out += _capped(lines, len(lines), config) + [""]

    if digest.done_today:
        out += ["## Done today", ""]
        lines = [_task_line(t, config, done=True) for t in digest.done_today]
        out += _capped(lines, len(lines), config) + [""]

    if urgent:
        out += ["## Needs attention", ""]
        lines = [_task_line(t, config) for t in urgent]
        out += _capped(lines, len(lines), config) + [""]
    return "\n".join(out)
