"""The rules of the nightly job (RP-18, section 3). No LLM.

Input: the notes from collect.py. Output: a Digest (tasks, events, notes)
that render.py turns into todo.md and daily_brief.md.

Where tasks come from
  * Checkbox lines in any note:  "- [ ] send the budget"  (open)
                                  "- [x] send the budget"  (done)
  * An Inbox note with no checkbox is one reminder: its title is the task.

Cross-session rules (a "session" is one plan, i.e. one conversation)
  1. Same task, many sessions: tasks with the same words (case, spaces and
     punctuation ignored) are ONE task. We keep the first and last time seen
     and how many times it was mentioned.
  2. Done or open: the latest mention wins. "- [x]" after "- [ ]" closes it;
     a later "- [ ]" opens it again.
  3. Calendar flag: a task whose words match an event title is "scheduled"
     (handled) when that event has synced_to_calendar: true. A task from the
     same plan as exactly one event is only LINKED to it (for priority): the
     meeting being booked does not mean the task is done.
  4. Carried over: an open task first seen before today's window.

Priority (1 = do first). Untuned guesses, easy to change:
  1  event NOT in the calendar, task with an urgent word, or task linked to
     a meeting in the next 24 hours
  2  task carried over for stale_after_days or more, or mentioned 2+ times
  3  everything else
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .collect import VaultNote
from .config import CompactionConfig

_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[( |x|X)\]\s+(\S.*?)\s*$")


def normalize(text: str) -> str:
    """Words only: lower case, no punctuation, single spaces. Keeps Sinhala/Tamil marks."""
    text = unicodedata.normalize("NFKC", text).casefold()
    kept = [ch if unicodedata.category(ch)[0] in ("L", "N", "M") else " " for ch in text]
    return " ".join("".join(kept).split())


def one_line(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@dataclass(frozen=True)
class Mention:
    text: str
    done: bool
    note: VaultNote


@dataclass
class Event:
    title: str
    start: datetime | None
    attendees: tuple[str, ...]
    synced: bool
    created: datetime
    notes: list[VaultNote] = field(default_factory=list)

    @property
    def key(self) -> str:
        return normalize(self.title)


@dataclass
class Task:
    key: str
    text: str
    first_seen: datetime
    last_seen: datetime
    mentions: int
    done: bool
    done_at: datetime | None
    sources: list[VaultNote]
    event: Event | None = None
    matched_by: str | None = None  # "title" or "plan"
    priority: int = 3
    reasons: list[str] = field(default_factory=list)

    @property
    def scheduled(self) -> bool:
        return self.matched_by == "title" and self.event is not None and self.event.synced


@dataclass
class Digest:
    now: datetime
    window_start: datetime
    open_tasks: list[Task]  # sorted: priority, then oldest first
    scheduled_tasks: list[Task]  # handled by a synced calendar event
    done_today: list[Task]
    events: list[Event]  # all known events, sorted by start
    new_notes: list[VaultNote]  # notes (not event records) created in the window
    skipped: dict[str, int]

    @property
    def unsynced_events(self) -> list[Event]:
        return [e for e in self.events if not e.synced]


def find_mentions(notes: list[VaultNote]) -> list[Mention]:
    mentions: list[Mention] = []
    for note in notes:
        if note.kind == "event":
            continue
        found = False
        for line in note.body.split("\n"):
            match = _CHECKBOX.match(line)
            if match and normalize(match.group(2)):
                mentions.append(Mention(match.group(2), match.group(1) != " ", note))
                found = True
        if not found and note.folder == "Inbox" and normalize(note.title):
            mentions.append(Mention(note.title, False, note))
    return mentions


def merge_events(notes: list[VaultNote]) -> list[Event]:
    """Rule 1 for events: same title and same start is one event (re-runs make copies)."""
    merged: dict[tuple, Event] = {}
    for note in notes:
        if note.kind != "event":
            continue
        key = (normalize(note.title), note.start)
        event = merged.get(key)
        if event is None:
            event = Event(note.title, note.start, note.attendees, bool(note.synced), note.created)
            merged[key] = event
        event.synced = event.synced or bool(note.synced)
        event.notes.append(note)
    far = datetime.max.replace(tzinfo=None)
    return sorted(
        merged.values(),
        key=lambda e: (e.start.replace(tzinfo=None) if e.start else far, e.key),
    )


def merge_tasks(mentions: list[Mention]) -> list[Task]:
    """Rules 1 and 2."""
    tasks: dict[str, Task] = {}
    for mention in sorted(mentions, key=lambda m: (m.note.created, m.note.path)):
        key = normalize(mention.text)
        task = tasks.get(key)
        if task is None:
            task = Task(
                key=key,
                text=mention.text,
                first_seen=mention.note.created,
                last_seen=mention.note.created,
                mentions=0,
                done=False,
                done_at=None,
                sources=[],
            )
            tasks[key] = task
        task.mentions += 1
        task.last_seen = mention.note.created
        task.done = mention.done  # the latest mention wins
        task.done_at = mention.note.created if mention.done else None
        if mention.note not in task.sources:
            task.sources.append(mention.note)
    return list(tasks.values())


def link_events(tasks: list[Task], events: list[Event]) -> None:
    """Rule 3."""
    by_plan: dict[str, list[Event]] = {}
    for event in events:
        for note in event.notes:
            if note.plan:
                by_plan.setdefault(note.plan, []).append(event)
    for task in tasks:
        words = set(task.key.split())
        for event in events:
            event_words = set(event.key.split())
            if task.key == event.key or (len(event_words) >= 2 and event_words <= words):
                task.event, task.matched_by = event, "title"
                break
        if task.event is None:
            plans = {n.plan for n in task.sources if n.plan}
            linked = {id(e): e for p in plans for e in by_plan.get(p, [])}
            if len(linked) == 1:
                task.event, task.matched_by = next(iter(linked.values())), "plan"


def set_priority(task: Task, config: CompactionConfig, now: datetime, window_start: datetime) -> None:
    words = set(task.key.split())
    urgent = sorted(words & set(config.urgent_words))
    if urgent:
        task.reasons.append("urgent word: " + ", ".join(urgent))
    event = task.event
    if event and event.start and now <= event.start <= now + timedelta(hours=24):
        task.reasons.append(f"meeting {event.start:%a %H:%M}")
    if task.first_seen < window_start:
        days = (now - task.first_seen).days
        task.reasons.append(f"carried over {days} day(s)" if days else "carried over")
        stale = days >= config.stale_after_days
    else:
        stale = False
    if task.mentions >= 2:
        task.reasons.append(f"mentioned {task.mentions} times")

    if urgent or (event and event.start and now <= event.start <= now + timedelta(hours=24)):
        task.priority = 1
    elif stale or task.mentions >= 2:
        task.priority = 2
    else:
        task.priority = 3


def build_digest(
    notes: list[VaultNote],
    config: CompactionConfig,
    now: datetime,
    skipped: dict[str, int] | None = None,
) -> Digest:
    window_start = now - timedelta(hours=config.window_hours)
    events = merge_events(notes)
    tasks = merge_tasks(find_mentions(notes))
    link_events(tasks, events)

    open_tasks, scheduled, done_today = [], [], []
    for task in tasks:
        if task.done:
            if task.done_at and task.done_at >= window_start:
                done_today.append(task)
        elif task.scheduled and task.event.start and task.event.start >= now:
            scheduled.append(task)
        else:
            set_priority(task, config, now, window_start)
            open_tasks.append(task)
    open_tasks.sort(key=lambda t: (t.priority, t.first_seen, t.key))
    done_today.sort(key=lambda t: (t.done_at, t.key))
    scheduled.sort(key=lambda t: (t.event.start, t.key))

    new_notes = [n for n in notes if n.kind != "event" and n.created >= window_start]
    return Digest(
        now=now,
        window_start=window_start,
        open_tasks=open_tasks,
        scheduled_tasks=scheduled,
        done_today=done_today,
        events=events,
        new_notes=new_notes,
        skipped=dict(skipped or {}),
    )
