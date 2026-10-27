"""Tool-use orchestrator (RP-16, section 4a).

Takes the final ActionPlan from RP-14 and sends each note to the filesystem
MCP server and each event to the calendar MCP server. No LLM here: plain rules.

Both servers stay connected for the whole session (starting a server costs
seconds, a call costs milliseconds). One failing item never stops the others.
The report never holds meeting text: only kind, position, status, a code,
a path or id, and the time the call took.
"""

from __future__ import annotations

import logging
import re
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

from agentic_core.decoding.plan_schema import ActionPlan, PlannedEvent, PlannedNote

logger = logging.getLogger("agentic_core.orchestrator")

# Only codes made by our own servers may enter a report. Anything else is TOOL_ERROR.
_SAFE_CODE = re.compile(r"(?:BLOCKED|REJECTED):[A-Z_]{1,40}|BACKEND_ERROR|IO_ERROR")

REPO_ROOT = Path(__file__).resolve().parents[2]


class OrchestratorError(Exception):
    """The orchestrator itself could not work. The message is only a reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ItemResult:
    kind: str  # "note" or "event"
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


class Orchestrator:
    """Use as: async with Orchestrator(fs_target, cal_target) as o: await o.run_plan(plan)."""

    def __init__(self, filesystem: Any, calendar: Any) -> None:
        self._filesystem_target = filesystem
        self._calendar_target = calendar
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
        items: list[ItemResult] = []
        for index, note in enumerate(plan.notes):
            items.append(await self._send_note(index, note))
        for index, event in enumerate(plan.events):
            items.append(await self._send_event(index, event))
        report = RunReport(tuple(items))
        logger.info(
            "plan done: %d item(s), %d failed, %.0f ms",
            len(items),
            len(report.failed),
            report.total_ms,
        )
        return report

    async def _send_note(self, index: int, note: PlannedNote) -> ItemResult:
        arguments = {
            "folder": note.folder,
            "title": note.title,
            "content": f"# {note.title}\n\n{note.body}\n",
        }
        data, code, ms = await self._call(self._filesystem, "write_note", arguments)
        if code is None and not (isinstance(data, dict) and isinstance(data.get("path"), str)):
            code = "BAD_RESPONSE"
        if code is not None:
            return ItemResult("note", index, "failed", code, None, ms)
        return ItemResult("note", index, "written", None, data["path"], ms)

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