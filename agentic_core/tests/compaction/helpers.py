"""Builds small synthetic vaults for the compaction tests. Not evaluation data."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agentic_core.mcp_servers import note_header

ZONE = ZoneInfo("Asia/Colombo")
NOW = datetime(2026, 11, 17, 20, 0, tzinfo=ZONE)  # the 8:00 PM run


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ZONE)


def make_vault(root: Path) -> Path:
    vault = root / "vault"
    for zone in ("Inbox", "Meetings", "Ideas"):
        (vault / zone).mkdir(parents=True)
    return vault


def add_note(
    vault: Path,
    path: str,
    title: str,
    body: str,
    created: str,
    plan: str | None = "p1",
) -> Path:
    fields = {"type": "note", "created": at(created).isoformat(), "synced_to_calendar": False}
    if plan:
        fields["plan"] = plan
    target = vault / path
    target.write_text(note_header.render(fields) + f"# {title}\n\n{body}\n", encoding="utf-8")
    return target


def add_event(
    vault: Path,
    path: str,
    title: str,
    start: str,
    created: str,
    synced: bool = True,
    plan: str | None = "p1",
    attendees: tuple[str, ...] = (),
) -> Path:
    fields = {
        "type": "event",
        "created": at(created).isoformat(),
        "plan": plan,
        "start": start,
        "attendees": list(attendees),
        "synced_to_calendar": synced,
        "calendar_status": "created" if synced else "failed",
    }
    target = vault / path
    target.write_text(note_header.render(fields) + f"# {title}\n\nStart: {start}\n", encoding="utf-8")
    return target


def add_plain(vault: Path, path: str, text: str, modified: str) -> Path:
    """A note without a header (written by hand). Its time is the file's change time."""
    target = vault / path
    target.write_text(text, encoding="utf-8")
    stamp = at(modified).timestamp()
    os.utime(target, (stamp, stamp))
    return target
