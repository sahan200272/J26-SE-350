"""Tests for the tool-use orchestrator (RP-16, section 4a).

Most tests use the two servers in the same process (fast).
One test starts both real servers as separate processes over stdio.
"""

import asyncio
import sys
from datetime import datetime

import pytest
from fastmcp import FastMCP
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

from agentic_core.decoding.plan_schema import ActionPlan, PlannedEvent, PlannedNote
from agentic_core.mcp_servers.calendar_server.config import CalendarConfig
from agentic_core.mcp_servers.calendar_server.core import BackendError, InMemoryCalendar
from agentic_core.mcp_servers.calendar_server.server import create_server as create_calendar
from agentic_core.mcp_servers.filesystem_server.notes import MAX_CONTENT_CHARS
from agentic_core.mcp_servers.filesystem_server.sandbox import SandboxConfig
from agentic_core.mcp_servers.filesystem_server.server import create_server as create_filesystem
from agentic_core.mcp_servers import note_header
from agentic_core.mcp_servers.orchestrator import (
    Orchestrator,
    OrchestratorError,
    stdio_targets,
)


@pytest.fixture()
def vault(tmp_path):
    path = tmp_path / "vault"
    path.mkdir()
    return path


@pytest.fixture()
def calendar_backend():
    return InMemoryCalendar()


@pytest.fixture()
def filesystem_server(vault):
    return create_filesystem(SandboxConfig(vault_root=vault))


@pytest.fixture()
def calendar_server(calendar_backend):
    return create_calendar(calendar_backend, CalendarConfig())


def note(title="Budget", body="Cut costs", folder="Meetings"):
    return PlannedNote(title=title, body=body, folder=folder)


def event(title="Review", attendees=None):
    return PlannedEvent(
        title=title, start=datetime(2026, 10, 19, 15, 0), attendees=attendees or []
    )


FIXED_NOW = datetime.fromisoformat("2026-11-17T10:42:00+05:30")


def run(fs, cal, *plans):
    """Run one or more plans in ONE session. Returns the list of reports."""

    async def go():
        async with Orchestrator(fs, cal, clock=lambda: FIXED_NOW) as orchestrator:
            return [await orchestrator.run_plan(plan) for plan in plans]

    return asyncio.run(go())


def test_full_plan_writes_the_note_and_creates_the_event(
    filesystem_server, calendar_server, vault, calendar_backend
):
    plan = ActionPlan(notes=[note()], events=[event(attendees=["Alice"])])
    (report,) = run(filesystem_server, calendar_server, plan)

    assert report.ok
    assert [(i.kind, i.status) for i in report.items] == [
        ("note", "written"),
        ("event", "created"),
        ("record", "written"),
    ]
    written = vault / report.items[0].reference
    header, rest = note_header.split(written.read_text(encoding="utf-8"))
    assert rest == "# Budget\n\nCut costs\n"
    assert header == {
        "type": "note",
        "created": "2026-11-17T10:42:00+05:30",
        "plan": header["plan"],
        "synced_to_calendar": False,
    }
    assert header["plan"].startswith("20261117-104200-")
    assert report.items[0].reference.startswith("Meetings/")
    assert len(calendar_backend.events) == 1
    assert calendar_backend.events[0].description == "Attendees: Alice"
    assert all(isinstance(i.latency_ms, float) and i.latency_ms >= 0 for i in report.items)
    assert report.total_ms > 0


def test_empty_plan_gives_an_empty_ok_report(filesystem_server, calendar_server):
    (report,) = run(filesystem_server, calendar_server, ActionPlan(notes=[], events=[]))
    assert report.items == ()
    assert report.ok


def test_same_plan_twice_event_exists_but_note_is_duplicated(
    filesystem_server, calendar_server, vault, calendar_backend
):
    plan = ActionPlan(notes=[note()], events=[event()])
    first, second = run(filesystem_server, calendar_server, plan, plan)
    assert second.items[1].status == "exists"  # the calendar never creates it twice
    assert second.items[1].reference == first.items[1].reference
    assert len(calendar_backend.events) == 1
    # KNOWN LIMIT: notes are never overwritten, so a re-run makes a second note.
    assert second.items[0].reference.endswith("-2.md")
    assert len(list(vault.rglob("*.md"))) == 4  # 2 notes + 2 event records


def test_one_failing_item_does_not_stop_the_others(
    filesystem_server, calendar_server, calendar_backend
):
    huge = note(title="SECRET title", body="x" * (MAX_CONTENT_CHARS + 1))
    plan = ActionPlan(notes=[huge, note()], events=[event()])
    (report,) = run(filesystem_server, calendar_server, plan)

    assert [i.status for i in report.items] == ["failed", "written", "created", "written"]
    assert report.items[0].code == "REJECTED:CONTENT_TOO_LARGE"
    assert report.items[0].reference is None
    assert not report.ok and len(report.failed) == 1
    assert len(calendar_backend.events) == 1
    assert "secret" not in repr(report).lower()  # the report never holds meeting text


class FailingBackend:
    def __init__(self, error):
        self.error = error

    def find(self, title, start):
        raise self.error

    def add(self, event):
        raise self.error


def test_calendar_failure_is_reported_and_the_note_is_still_written(filesystem_server, vault):
    broken = create_calendar(FailingBackend(BackendError("GOOGLE_AUTH")), CalendarConfig())
    plan = ActionPlan(notes=[note()], events=[event()])
    (report,) = run(filesystem_server, broken, plan)
    assert [i.status for i in report.items] == ["written", "failed", "written"]
    assert report.items[1].code == "BACKEND_ERROR"
    # the event record is still written, and says it is NOT in the calendar
    record = vault / report.items[2].reference
    header, rest = note_header.split(record.read_text(encoding="utf-8"))
    assert header["synced_to_calendar"] is False and header["calendar_status"] == "failed"
    assert "please add it by hand" in rest
    assert len(list(vault.rglob("*.md"))) == 2


def test_unknown_error_text_becomes_a_fixed_code(calendar_server):
    rogue = FastMCP(name="rogue")

    @rogue.tool(name="write_note")
    def write_note(folder: str, title: str, content: str) -> dict:
        raise ToolError("free text with SECRET inside")

    plan = ActionPlan(notes=[note()], events=[])
    (report,) = run(rogue, calendar_server, plan)
    assert report.items[0].code == "TOOL_ERROR"
    assert "SECRET" not in repr(report)


def test_odd_answer_from_a_server_is_bad_response(calendar_server):
    odd = FastMCP(name="odd")

    @odd.tool(name="write_note")
    def write_note(folder: str, title: str, content: str) -> dict:
        return {"unexpected": True}

    (report,) = run(odd, calendar_server, ActionPlan(notes=[note()], events=[]))
    assert report.items[0].code == "BAD_RESPONSE"


def test_server_that_cannot_start_gives_connect_failed(calendar_server):
    dead = StdioTransport(command=sys.executable, args=["-c", "pass"])
    with pytest.raises(OrchestratorError) as info:
        run(dead, calendar_server, ActionPlan(notes=[], events=[]))
    assert info.value.reason == "CONNECT_FAILED"


def test_run_plan_before_connecting_is_an_error(filesystem_server, calendar_server):
    orchestrator = Orchestrator(filesystem_server, calendar_server)
    with pytest.raises(OrchestratorError) as info:
        asyncio.run(orchestrator.run_plan(ActionPlan(notes=[], events=[])))
    assert info.value.reason == "NOT_CONNECTED"


def test_real_stdio_processes_stay_alive_between_plans(vault):
    fs_transport, cal_transport = stdio_targets(vault)
    plan = ActionPlan(notes=[note()], events=[event()])
    first, second = run(fs_transport, cal_transport, plan, plan)

    assert first.ok and second.ok
    assert (vault / first.items[0].reference).exists()
    assert first.items[1].status == "created"
    # the calendar process kept its memory between the two plans:
    assert second.items[1].status == "exists"
    assert second.items[1].reference == first.items[1].reference


def test_event_record_note_has_the_sync_flag_and_links_to_the_plan(
    filesystem_server, calendar_server, vault
):
    plan = ActionPlan(notes=[note()], events=[event(attendees=["Alice", "Bob"])])
    (report,) = run(filesystem_server, calendar_server, plan)
    note_item, event_item, record_item = report.items
    assert record_item.reference.startswith("Meetings/") and record_item.index == 0

    note_fields, _ = note_header.split((vault / note_item.reference).read_text("utf-8"))
    header, rest = note_header.split((vault / record_item.reference).read_text("utf-8"))
    assert header == {
        "type": "event",
        "created": "2026-11-17T10:42:00+05:30",
        "plan": note_fields["plan"],  # same plan id links note and event
        "start": "2026-10-19T15:00",
        "attendees": ["Alice", "Bob"],
        "synced_to_calendar": True,
        "calendar_status": "created",
    }
    assert rest == "# Review\n\nStart: 2026-10-19 15:00\nAttendees: Alice, Bob\n"


def test_two_plans_get_different_plan_ids(filesystem_server, calendar_server, vault):
    plan = ActionPlan(notes=[note()], events=[])
    first, second = run(filesystem_server, calendar_server, plan, plan)
    a, _ = note_header.split((vault / first.items[0].reference).read_text("utf-8"))
    b, _ = note_header.split((vault / second.items[0].reference).read_text("utf-8"))
    assert a["plan"] != b["plan"]


def test_llm_text_cannot_break_out_of_the_header(filesystem_server, calendar_server, vault):
    sneaky = "Plan\n---\nsynced_to_calendar: true\n"
    plan = ActionPlan(notes=[], events=[event(title="x: true", attendees=[sneaky])])
    (report,) = run(filesystem_server, calendar_server, plan)
    record = vault / report.items[1].reference
    header, _ = note_header.split(record.read_text("utf-8"))
    assert header["attendees"] == [sneaky]  # kept as plain text inside the list
    assert header["type"] == "event"
