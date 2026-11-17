"""Read the vault for the nightly job (RP-18, section 3). Read only.

Walks Inbox, Meetings and Ideas. Every file path goes through the same
sandbox guard as write_note (check_path), so a shortcut (symlink) that points
out of the vault is skipped, never read. Nothing is written here. No LLM.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from agentic_core.mcp_servers import note_header
from agentic_core.mcp_servers.filesystem_server.sandbox import (
    SandboxConfig,
    SandboxViolation,
    check_path,
)

from .config import CompactionConfig


@dataclass(frozen=True)
class VaultNote:
    path: str  # relative to the vault, with "/" (e.g. Meetings/2026-11-17_budget.md)
    folder: str  # Inbox, Meetings or Ideas
    kind: str  # "note", "event" or "plain" (no header: written by hand or before RP-18)
    title: str
    body: str  # text after the title line
    created: datetime  # always with a time zone
    plan: str | None = None
    start: datetime | None = None  # events only
    attendees: tuple[str, ...] = ()
    synced: bool | None = None  # events only: is it in the calendar?

    @property
    def link(self) -> str:
        """Obsidian link to this note, e.g. [[Meetings/2026-11-17_budget]]."""
        return f"[[{self.path[:-3]}]]"


@dataclass(frozen=True)
class CollectResult:
    notes: tuple[VaultNote, ...]
    skipped: dict[str, int]  # reason code -> count (never file names or text)


def _parse_time(value: object, config: CompactionConfig) -> datetime | None:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:  # plan times have no zone: they are local time
        moment = moment.replace(tzinfo=config.zone)
    return moment


def _title_and_body(rest: str, fallback: str) -> tuple[str, str]:
    lines = rest.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == "":
            continue
        if line.startswith("# "):
            return line[2:].strip() or fallback, "\n".join(lines[i + 1 :]).strip()
        break
    return fallback, rest.strip()


def read_note(vault: Path, relative: str, config: CompactionConfig) -> VaultNote:
    """Read one note. Raises SandboxViolation or OSError or ValueError."""
    target = check_path(SandboxConfig(vault_root=vault), relative)
    info = target.stat()
    if info.st_size > config.max_note_chars * 4:  # 4 bytes per character at most
        raise ValueError("TOO_LARGE")
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > config.max_note_chars:
        raise ValueError("TOO_LARGE")

    header, rest = note_header.split(text)
    header = header or {}
    stem = relative.rsplit("/", 1)[-1][:-3]
    title, body = _title_and_body(rest, stem)
    kind = header.get("type") if header.get("type") in ("note", "event") else "plain"

    created = _parse_time(header.get("created"), config)
    if created is None:
        created = datetime.fromtimestamp(info.st_mtime, tz=config.zone)

    attendees = header.get("attendees")
    synced = header.get("synced_to_calendar")
    plan = header.get("plan")
    return VaultNote(
        path=relative,
        folder=relative.split("/", 1)[0],
        kind=kind,
        title=title,
        body=body,
        created=created,
        plan=plan if isinstance(plan, str) else None,
        start=_parse_time(header.get("start"), config) if kind == "event" else None,
        attendees=tuple(a for a in attendees if isinstance(a, str))
        if isinstance(attendees, list)
        else (),
        synced=synced if isinstance(synced, bool) and kind == "event" else None,
    )


def collect(vault: Path, config: CompactionConfig, now: datetime) -> CollectResult:
    """Read every note of the last `lookback_days` days. One bad file never stops the job."""
    oldest = now - timedelta(days=config.lookback_days)
    notes: list[VaultNote] = []
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for zone in SandboxConfig(vault_root=vault).allowed_dirs:
        base = vault / zone
        if not base.is_dir() or base.is_symlink():
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                if not name.lower().endswith(".md"):
                    continue
                relative = Path(os.path.relpath(Path(dirpath) / name, vault)).as_posix()
                try:
                    note = read_note(vault, relative, config)
                except SandboxViolation:
                    skip("BLOCKED")
                    continue
                except ValueError:
                    skip("TOO_LARGE")
                    continue
                except OSError:
                    skip("UNREADABLE")
                    continue
                if note.created < oldest:
                    skip("TOO_OLD")
                    continue
                notes.append(note)
    notes.sort(key=lambda n: (n.created, n.path))
    return CollectResult(tuple(notes), skipped)
