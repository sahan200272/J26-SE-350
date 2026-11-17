"""Tests for the FastMCP filesystem server (RP-16, section 2b).

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

from agentic_core.mcp_servers.filesystem_server.sandbox import SandboxConfig
from agentic_core.mcp_servers.filesystem_server.server import create_server

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def vault(tmp_path):
    path = tmp_path / "vault"
    path.mkdir()
    return path


@pytest.fixture()
def server(vault):
    return create_server(SandboxConfig(vault_root=vault))


def call(target, tool, arguments):
    """Call one tool and return the result. Raises ToolError on a tool error."""

    async def run():
        async with Client(target) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def test_only_the_two_write_tools_are_offered(server):
    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    names = sorted(tool.name for tool in asyncio.run(run()))
    assert names == ["write_digest", "write_note"]  # no read, list or delete


def test_write_note_creates_the_file(server, vault):
    result = call(server, "write_note", {"folder": "Ideas", "title": "Budget", "content": "Hello"})
    relative = result.data["path"]
    assert relative.startswith("Ideas/") and relative.endswith("_budget.md")
    assert (vault / relative).read_text(encoding="utf-8") == "Hello\n"


@pytest.mark.parametrize(
    "folder, reason",
    [
        ("../outside", "TRAVERSAL"),
        ("../../etc/passwd", "TRAVERSAL"),
        ("Inbox/../../x", "TRAVERSAL"),
        ("/etc", "ABSOLUTE"),
        ("C:\\Windows", "DRIVE_OR_STREAM"),
        ("Secrets", "NOT_ALLOWED_DIR"),
        ("Inbox\x00evil", "NULL_BYTE"),
    ],
)
def test_bad_folder_is_blocked_and_nothing_is_written(server, vault, folder, reason):
    with pytest.raises(ToolError) as info:
        call(server, "write_note", {"folder": folder, "title": "x", "content": "y"})
    assert f"BLOCKED:{reason}" in str(info.value)
    assert not any(vault.rglob("*.md"))
    assert not any(vault.parent.rglob("*.md"))  # nothing escaped next to the vault either


def test_bad_content_is_rejected(server):
    with pytest.raises(ToolError) as info:
        call(server, "write_note", {"folder": "Inbox", "title": "x", "content": "   "})
    assert "REJECTED:EMPTY_CONTENT" in str(info.value)


def test_error_text_never_contains_the_vault_path(server, vault):
    with pytest.raises(ToolError) as info:
        call(server, "write_note", {"folder": "../x", "title": "t", "content": "c"})
    assert str(vault) not in str(info.value)


@pytest.mark.parametrize(
    "arguments",
    [
        {"folder": "Inbox", "title": "SECRET", "content": ["SECRET"]},  # wrong type
        {"folder": "Inbox", "title": 123, "content": "SECRET"},  # wrong type
        {"folder": "Inbox", "title": "SECRET"},  # missing argument
        {"folder": "Inbox", "title": "t", "content": "c", "extra": "SECRET"},  # extra argument
    ],
    ids=["wrong-type-list", "wrong-type-number", "missing-argument", "extra-argument"],
)
def test_bad_arguments_give_a_fixed_code_and_never_echo_the_input(server, arguments):
    with pytest.raises(ToolError) as info:
        call(server, "write_note", arguments)
    assert str(info.value) == "REJECTED:BAD_ARGUMENTS"
    assert "SECRET" not in str(info.value)


def test_real_stdio_process_end_to_end(vault):
    transport = StdioTransport(
        command=sys.executable,
        args=[
            "-m",
            "agentic_core.mcp_servers.filesystem_server.server",
            "--vault",
            str(vault),
        ],
        cwd=str(REPO_ROOT),
    )

    async def run():
        async with Client(transport) as client:
            ok = await client.call_tool(
                "write_note", {"folder": "Meetings", "title": "Standup", "content": "notes"}
            )
            try:
                await client.call_tool(
                    "write_note", {"folder": "../../etc/passwd", "title": "x", "content": "y"}
                )
                blocked = None
            except ToolError as error:
                blocked = str(error)
            return ok, blocked

    ok, blocked = asyncio.run(run())
    assert (vault / ok.data["path"]).exists()
    assert "BLOCKED:TRAVERSAL" in blocked