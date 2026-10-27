"""Harness for the path-traversal escape test (RP-16, section 4c).

For every hostile vector it builds a fresh temporary world (a vault with three
allowed folders, a canary file outside it) and sends the vector to the real
filesystem MCP tool, as the `folder` and, where possible, as the `title`.

Two phases protect the real disk:
  1. Pre-check: ask the guard where the note would go. If an independent check
     says "outside the allowed folders", the vector counts as an ESCAPE and
     nothing is written.
  2. Call: send the vector through MCP, then compare a snapshot of everything
     outside the allowed folders. Any new, changed or removed item is an ESCAPE.

Verdicts: blocked, rejected, harmless (written safely inside an allowed folder),
escape, error (unexpected crash), not_run (could not set up, e.g. no symlinks).
Outcomes never contain meeting text. Evidence is limited to a few short paths.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from agentic_core.mcp_servers.filesystem_server import notes
from agentic_core.mcp_servers.filesystem_server.sandbox import SandboxConfig, SandboxViolation
from agentic_core.mcp_servers.filesystem_server.server import create_server

ZONES = ("Inbox", "Meetings", "Ideas")
POSITIONS = ("folder", "title")

ServerFactory = Callable[[Path], FastMCP]


@dataclass(frozen=True)
class VectorOutcome:
    vector_id: str
    category: str
    position: str  # "folder" or "title"
    verdict: str  # blocked, rejected, harmless, escape, error, not_run
    detail: str  # a reason code or a short tag
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class SuiteResult:
    outcomes: tuple[VectorOutcome, ...]

    @property
    def escaped_ids(self) -> list[str]:
        return sorted({o.vector_id for o in self.outcomes if o.verdict == "escape"})

    @property
    def vectors_run(self) -> int:
        return len({o.vector_id for o in self.outcomes if o.verdict != "not_run"})

    @property
    def escape_rate(self) -> float:
        run = self.vectors_run
        return len(self.escaped_ids) / run if run else 0.0

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for outcome in self.outcomes:
            result[outcome.verdict] = result.get(outcome.verdict, 0) + 1
        return result


def default_server_factory(vault: Path) -> FastMCP:
    return create_server(SandboxConfig(vault_root=vault))


# ---------- independent checks (they do not use the guard's own code) ----------


def _is_within(path: str, base: str) -> bool:
    try:
        return os.path.commonpath([path, base]) == base
    except ValueError:  # different drives, or an unusable path
        return False


def _inside_allowed_zone(target: Path, vault: Path) -> bool:
    """True only if the target really lives under vault/Inbox, Meetings or Ideas."""
    vault_real = os.path.realpath(vault)
    real = os.path.realpath(target)
    return any(_is_within(real, os.path.join(vault_real, zone)) for zone in ZONES)


def snapshot(world: Path, vault: Path) -> dict[str, tuple]:
    """Everything in the world except the CONTENT of the three allowed folders."""
    skip = {vault / zone for zone in ZONES}
    items: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(world, followlinks=False):
        here = Path(dirpath)
        descend = []
        for name in dirnames:
            full = here / name
            rel = os.path.relpath(full, world)
            if full in skip:
                items[rel] = ("zone",)
            elif full.is_symlink():
                items[rel] = ("symlink", os.readlink(full))
            else:
                items[rel] = ("dir",)
                descend.append(name)
        dirnames[:] = descend
        for name in filenames:
            full = here / name
            rel = os.path.relpath(full, world)
            if full.is_symlink():
                items[rel] = ("symlink", os.readlink(full))
            else:
                info = full.stat()
                items[rel] = ("file", info.st_size, info.st_mtime_ns)
    return items


def _changes(before: dict[str, tuple], after: dict[str, tuple]) -> list[str]:
    changed = [k for k in after if before.get(k) != after[k]]
    changed += [k for k in before if k not in after]
    return sorted(changed)


# ---------- one vector ----------


def _arguments(vector: str, position: str) -> dict[str, str]:
    if position == "folder":
        return {"folder": vector, "title": "probe", "content": "probe content"}
    return {"folder": "Inbox", "title": vector, "content": "probe content"}


def _apply_setup(setup: str | None, vault: Path, outside: Path) -> bool:
    if setup is None:
        return True
    if setup not in ("symlink_in_zone", "symlink_zone"):
        raise ValueError("unknown setup in the dataset")
    try:
        if setup == "symlink_in_zone":
            os.symlink(outside, vault / "Ideas" / "link", target_is_directory=True)
        else:
            (vault / "Inbox").rmdir()
            os.symlink(outside, vault / "Inbox", target_is_directory=True)
    except OSError:
        return False
    return True


def _precheck(vault: Path, arguments: dict[str, str]) -> tuple[str, str | None]:
    """Ask the guard where the note would go. Mirrors how write_note builds the path."""
    relative = f"{arguments['folder']}/{date.today().isoformat()}_{notes.make_slug(arguments['title'])}.md"
    try:
        target = notes.check_path(SandboxConfig(vault_root=vault), relative)
    except SandboxViolation as violation:
        return "blocked", violation.reason
    except Exception as error:
        return "error", type(error).__name__
    try:
        inside = _inside_allowed_zone(target, vault)
    except (ValueError, OSError):
        return "outside", "UNCHECKABLE"
    return ("inside" if inside else "outside"), str(target)


async def _call(server: FastMCP, arguments: dict[str, str]):
    async with Client(server) as client:
        return await client.call_tool("write_note", arguments)


def _short(text: str) -> str:
    return repr(text)[:120]


def run_vector(
    vector: dict,
    position: str,
    work_dir: Path,
    server_factory: ServerFactory = default_server_factory,
) -> VectorOutcome:
    vid, category = vector["id"], vector["category"]

    def outcome(verdict: str, detail: str, evidence: tuple[str, ...] = ()) -> VectorOutcome:
        return VectorOutcome(vid, category, position, verdict, detail, evidence)

    world = work_dir / f"{vid}-{position}"
    vault = world / "a" / "b" / "vault"
    outside = world / "outside"
    for zone in ZONES:
        (vault / zone).mkdir(parents=True)
    outside.mkdir()
    (outside / "canary.txt").write_text("untouched", encoding="utf-8")
    (vault / "canary_in_vault_root.txt").write_text("untouched", encoding="utf-8")

    if not _apply_setup(vector["setup"], vault, outside):
        return outcome("not_run", "NO_SYMLINK_PRIVILEGE")

    arguments = _arguments(vector["vector"], position)

    # Phase 1: nothing is written here.
    where, info = _precheck(vault, arguments)
    if where == "outside":
        return outcome("escape", "PRECHECK_OUTSIDE_ZONE", (_short(info or ""),))
    if where == "error":
        return outcome("error", f"PRECHECK_{info}")

    # Phase 2: the real MCP call, then compare the world.
    before = snapshot(world, vault)
    try:
        result = asyncio.run(_call(server_factory(vault), arguments))
        called: tuple[str, object] = ("ok", result.data)
    except ToolError as error:
        called = ("tool_error", str(error))
    except Exception as error:
        called = ("crash", type(error).__name__)
    changes = _changes(before, snapshot(world, vault))
    if changes:
        return outcome("escape", "OUTSIDE_CHANGED", tuple(_short(c) for c in changes[:3]))

    kind, value = called
    if kind == "ok":
        path = value.get("path") if isinstance(value, dict) else None
        if not isinstance(path, str):
            return outcome("error", "BAD_RESPONSE")
        written = vault / path
        if not written.is_file() or not _inside_allowed_zone(written, vault):
            return outcome("escape", "RESULT_OUTSIDE_ZONE", (_short(path),))
        return outcome("harmless", "WRITTEN_INSIDE_ZONE")
    if kind == "tool_error":
        message = str(value)
        if message.startswith("BLOCKED:"):
            return outcome("blocked", message)
        if message.startswith("REJECTED:"):
            return outcome("rejected", message)
        return outcome("error", "TOOL_ERROR")
    return outcome("error", f"CRASH_{value}")


def run_suite(
    vectors: list[dict],
    work_dir: Path,
    server_factory: ServerFactory = default_server_factory,
) -> SuiteResult:
    outcomes = []
    for vector in vectors:
        for position in POSITIONS:
            if position == "title" and vector["setup"] is not None:
                continue  # setups only make sense for the folder position
            outcomes.append(run_vector(vector, position, work_dir, server_factory))
    return SuiteResult(tuple(outcomes))