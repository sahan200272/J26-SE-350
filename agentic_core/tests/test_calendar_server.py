"""Tests for the FastMCP calendar server (RP-16, section 3b).

Most tests talk to the server in the same process (fast).
One test starts the real server as a separate process over stdio.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

from agentic_core.mcp_servers.calendar_server.config import CalendarConfig
from agentic_core.mcp_servers.calendar_server.core import BackendError, InMemoryCalendar
from agentic_core.mcp_servers.calendar_server.server import create_server

REPO_ROOT = Path(__file__).resolve().parents[2]
START = "2026-10-19T15:00"


@pytest.fixture()
def backend():
    return InMemoryCalendar()


@pytest.fixture()
def server(backend):
    return create_server(backend, CalendarConfig())


def call(target, arguments):
    """Call create_event and return the result. Raises ToolError on a tool error."""

    async def run():
        async with Client(target) as client:
            return await client.call_tool("create_event", arguments)

    return asyncio.run(run())


def test_only_one_tool_is_offered(server):
    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    assert [tool.name for tool in asyncio.run(run())] == ["create_event"]


def test_create_event_returns_the_event(server, backend):
    result = call(server, {"title": "Budget review", "start": START})
    assert result.data == {
        "status": "created",
        "event_id": "mem-1",
        "start": "2026-10-19T15:00:00+05:30",
        "end": "2026-10-19T16:00:00+05:30",
        "reminder_minutes": 10,
    }
    assert len(backend.events) == 1


def test_same_event_twice_gives_exists(server, backend):
    first = call(server, {"title": "Budget review", "start": START})
    again = call(server, {"title": "  budget REVIEW ", "start": START})
    assert again.data["status"] == "exists"
    assert again.data["event_id"] == first.data["event_id"]
    assert len(backend.events) == 1


def test_attendee_names_go_to_the_description(server, backend):
    call(server, {"title": "Sync", "start": START, "attendees": ["Alice", "Bob"]})
    assert backend.events[0].description == "Attendees: Alice, Bob"


@pytest.mark.parametrize(
    "arguments, reason",
    [
        ({"title": "x", "start": "2026-10-19T15:00:00+00:00"}, "TIMEZONE_NOT_ALLOWED"),
        ({"title": "x", "start": "tomorrow"}, "BAD_START"),
        ({"title": "   ", "start": START}, "BAD_TITLE"),
        ({"title": "x", "start": START, "reminder_minutes": True}, "BAD_REMINDER"),
        ({"title": "x", "start": START, "reminder_minutes": -1}, "BAD_REMINDER"),
        ({"title": "x", "start": START, "duration_minutes": "60"}, "BAD_DURATION"),
        ({"title": "x", "start": START, "duration_minutes": 0}, "BAD_DURATION"),
    ],
)
def test_bad_input_is_rejected_and_nothing_is_stored(server, backend, arguments, reason):
    with pytest.raises(ToolError) as info:
        call(server, arguments)
    assert str(info.value) == f"REJECTED:{reason}"
    assert backend.events == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"title": ["SECRET"], "start": START},  # wrong type
        {"title": "SECRET", "start": 5},  # wrong type
        {"title": "SECRET"},  # missing argument
        {"title": "t", "start": START, "extra": "SECRET"},  # extra argument
        {"title": "t", "start": START, "attendees": "SECRET"},  # not a list
    ],
    ids=["wrong-type-list", "wrong-type-number", "missing-argument", "extra-argument", "not-a-list"],
)
def test_bad_arguments_give_a_fixed_code_and_never_echo_the_input(server, backend, arguments):
    with pytest.raises(ToolError) as info:
        call(server, arguments)
    assert str(info.value) == "REJECTED:BAD_ARGUMENTS"
    assert "SECRET" not in str(info.value)
    assert backend.events == []


class FailingBackend:
    def __init__(self, error):
        self.error = error

    def find(self, title, start):
        raise self.error

    def add(self, event):
        raise self.error


def test_backend_error_gives_a_fixed_code():
    server = create_server(FailingBackend(BackendError("GOOGLE_AUTH")), CalendarConfig())
    with pytest.raises(ToolError) as info:
        call(server, {"title": "x", "start": START})
    assert str(info.value) == "BACKEND_ERROR"


def test_unexpected_crash_never_leaks_its_details(caplog):
    server = create_server(FailingBackend(RuntimeError("SECRET-DETAIL")), CalendarConfig())
    with caplog.at_level("ERROR", logger="agentic_core.calendar_server"):
        with pytest.raises(ToolError) as info:
            call(server, {"title": "x", "start": START})
    assert str(info.value) == "BACKEND_ERROR"
    assert "SECRET-DETAIL" not in caplog.text  # the log keeps the class name only
    assert "RuntimeError" in caplog.text


def test_real_stdio_process_end_to_end():
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "agentic_core.mcp_servers.calendar_server.server", "--backend", "memory"],
        cwd=str(REPO_ROOT),
    )

    async def run():
        async with Client(transport) as client:
            first = await client.call_tool("create_event", {"title": "Standup", "start": START})
            again = await client.call_tool("create_event", {"title": "Standup", "start": START})
            try:
                await client.call_tool(
                    "create_event", {"title": "x", "start": "2026-10-19T15:00:00Z"}
                )
                rejected = None
            except ToolError as error:
                rejected = str(error)
            return first, again, rejected

    first, again, rejected = asyncio.run(run())
    assert first.data["status"] == "created"
    assert again.data["status"] == "exists"
    assert again.data["event_id"] == first.data["event_id"]
    assert rejected == "REJECTED:TIMEZONE_NOT_ALLOWED"