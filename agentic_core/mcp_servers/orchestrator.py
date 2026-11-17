"""Tool-use orchestrator (RP-16, section 4a).

Takes the final ActionPlan from RP-14 and sends each note to the filesystem
MCP server and each event to the calendar MCP server. No LLM here: plain rules.

Both servers stay connected for the whole session (starting a server costs
seconds, a call costs milliseconds). One failing item never stops the others.
The report never holds meeting text: only kind, position, status, a code,
a path or id, and the time the call took.

RP-18, section 2: every note now starts with a small YAML header (see
note_header.py), and every event also gets a short record note in Meetings/
with synced_to_calendar true/false. The vault is then the full record of the
day, so the nightly compaction job only has to read the vault.
"""

from __future__ import annotations

import logging
import re
import secrets
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

from agentic_core.decoding.plan_schema import ActionPlan, PlannedEvent, PlannedNote
from agentic_core.mcp_servers import note_header

logger = logging.getLogger("agentic_core.orchestrator")

# Only codes made by our own servers may enter a report. Anything else is TOOL_ERROR.
_SAFE_CODE = re.compile(r"(?:BLOCKED|REJECTED):[A-Z_]{1,40}|BACKEND_ERROR|IO_ERROR")

REPO_ROOT = Path(__file__).resolve().parents[2]

# Event record notes go here (one short note per event).
RECORD_FOLDER = "Meetings"


class OrchestratorError(Exception):
    """The orchestrator itself could not work. The message is only a reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ItemResult:
    kind: str  # "note", "event" or "record" (the record note of an event)
    index: int  # position in the plan list
    status: str  # "written", "created", "exists" or "failed"
    code: str | None  # reason code when failed
    reference: str | None  # note path or event id when it worked
    latency_ms: float


@dataclass(frozen=True)
class RunReport:
    items: tuple[ItemResult, ...]

    @property
    def failed(self) -> tuple[ItemResult, ...]:
        return tuple(item for item in self.items if item.status == "failed")

    @property
    def ok(self) -> bool:
        return not self.failed

    @property
    def total_ms(self) -> float:
        return sum(item.latency_ms for item in self.items)


def stdio_targets(
    vault: Path, *, calendar_backend: str = "memory"
) -> tuple[StdioTransport, StdioTransport]:
    """Transports that start the two real servers as separate processes."""

    def transport(module: str, extra: list[str]) -> StdioTransport:
        return StdioTransport(
            command=sys.executable,
            args=["-m", f"agentic_core.mcp_servers.{module}.server", *extra],
            cwd=str(REPO_ROOT),
        )

    return (
        transport("filesystem_server", ["--vault", str(vault)]),
        transport("calendar_server", ["--backend", calendar_backend]),
    )


def _safe_code(message: str) -> str:
    return message if _SAFE_CODE.fullmatch(message) else "TOOL_ERROR"


def _local_now() -> datetime:
    return datetime.now().astimezone()


def new_plan_id(now: datetime) -> str:
    """Links all notes and events of one plan, e.g. 20261117-104200-3f2a."""
    return f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


class Orchestrator:
    """Use as: async with Orchestrator(fs_target, cal_target) as o: await o.run_plan(plan)."""

    def __init__(
        self,
        filesystem: Any,
        calendar: Any,
        *,
        clock: Callable[[], datetime] = _local_now,
    ) -> None:
        self._filesystem_target = filesystem
        self._calendar_target = calendar
        self._clock = clock
        self._stack: AsyncExitStack | None = None
        self._filesystem: Client | None = None
        self._calendar: Client | None = None

    async def __aenter__(self) -> "Orchestrator":
        stack = AsyncExitStack()
        try:
            self._filesystem = await stack.enter_async_context(Client(self._filesystem_target))
            self._calendar = await stack.enter_async_context(Client(self._calendar_target))
        except Exception as error:
            logger.error("cannot connect to a tool server: %s", type(error).__name__)
            try:
                await stack.aclose()
            except Exception:
                pass
            raise OrchestratorError("CONNECT_FAILED") from None
        self._stack = stack
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None

    async def run_plan(self, plan: ActionPlan) -> RunReport:
        if self._filesystem is None or self._calendar is None:
            raise OrchestratorError("NOT_CONNECTED")
        now = self._clock()
        stamp = {"created": now.isoformat(timespec="seconds"), "plan": new_plan_id(now)}
        items: list[ItemResult] = []
        for index, note in enumerate(plan.notes):
            items.append(await self._send_note(index, note, stamp))
        for index, event in enumerate(plan.events):
            result = await self._send_event(index, event)
            items.append(result)
            items.append(await self._send_record(index, event, result, stamp))
        report = RunReport(tuple(items))
        logger.info(
            "plan done: %d item(s), %d failed, %.0f ms",
            len(items),
            len(report.failed),
            report.total_ms,
        )
        return report

    async def _send_note(self, index: int, note: PlannedNote, stamp: dict) -> ItemResult:
        header = note_header.render({"type": "note", **stamp, "synced_to_calendar": False})
        content = f"{header}# {note.title}\n\n{note.body}\n"
        return await self._write("note", index, note.folder, note.title, content)

    async def _send_record(
        self, index: int, event: PlannedEvent, result: ItemResult, stamp: dict
    ) -> ItemResult:
        """Write the record note of one event, whether the calendar call worked or not."""
        synced = result.status in ("created", "exists")
        header = note_header.render(
            {
                "type": "event",
                **stamp,
                "start": event.start.isoformat(timespec="minutes"),
                "attendees": list(event.attendees),
                "synced_to_calendar": synced,
                "calendar_status": result.status,
            }
        )
        lines = [f"Start: {event.start:%Y-%m-%d %H:%M}"]
        if event.attendees:
            lines.append("Attendees: " + ", ".join(event.attendees))
        if not synced:
            lines.append("Not in the calendar yet: please add it by hand.")
        content = f"{header}# {event.title}\n\n" + "\n".join(lines) + "\n"
        return await self._write("record", index, RECORD_FOLDER, event.title, content)

    async def _write(
        self, kind: str, index: int, folder: str, title: str, content: str
    ) -> ItemResult:
        arguments = {"folder": folder, "title": title, "content": content}
        data, code, ms = await self._call(self._filesystem, "write_note", arguments)
        if code is None and not (isinstance(data, dict) and isinstance(data.get("path"), str)):
            code = "BAD_RESPONSE"
        if code is not None:
            return ItemResult(kind, index, "failed", code, None, ms)
        return ItemResult(kind, index, "written", None, data["path"], ms)

    async def _send_event(self, index: int, event: PlannedEvent) -> ItemResult:
        arguments = {
            "title": event.title,
            "start": event.start.isoformat(),
            "attendees": event.attendees,
        }
        data, code, ms = await self._call(self._calendar, "create_event", arguments)
        if code is None and not (
            isinstance(data, dict)
            and data.get("status") in ("created", "exists")
            and isinstance(data.get("event_id"), str)
        ):
            code = "BAD_RESPONSE"
        if code is not None:
            return ItemResult("event", index, "failed", code, None, ms)
        return ItemResult("event", index, data["status"], None, data["event_id"], ms)

    async def _call(
        self, client: Client, tool: str, arguments: dict[str, Any]
    ) -> tuple[Any, str | None, float]:
        started = time.perf_counter()
        data: Any = None
        code: str | None = None
        try:
            result = await client.call_tool(tool, arguments)
            data = result.data
        except ToolError as error:
            code = _safe_code(str(error))
        except Exception as error:  # connection lost, timeout, ...
            logger.error("call to %s failed: %s", tool, type(error).__name__)
            code = "TRANSPORT_ERROR"
        return data, code, (time.perf_counter() - started) * 1000.0