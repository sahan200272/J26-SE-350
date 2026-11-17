"""Tests for write_digest, the nightly root-file writer (RP-18, section 1)."""

import asyncio
import os

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from agentic_core.mcp_servers.filesystem_server import digest as digest_module
from agentic_core.mcp_servers.filesystem_server.digest import write_digest
from agentic_core.mcp_servers.filesystem_server.notes import NoteError
from agentic_core.mcp_servers.filesystem_server.sandbox import (
    SandboxConfig,
    SandboxViolation,
    check_digest_path,
)
from agentic_core.mcp_servers.filesystem_server.server import create_server


@pytest.fixture()
def vault(tmp_path):
    path = tmp_path / "vault"
    for zone in ("Inbox", "Meetings", "Ideas"):
        (path / zone).mkdir(parents=True)
    return path


@pytest.fixture()
def config(vault):
    return SandboxConfig(vault_root=vault)


def call(target, tool, arguments):
    async def run():
        async with Client(target) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


# ---------- the guard ----------


@pytest.mark.parametrize("name", ["todo.md", "daily_brief.md"])
def test_the_two_names_land_in_the_vault_root(config, vault, name):
    assert check_digest_path(config, name) == (vault / name).resolve()


@pytest.mark.parametrize(
    "name, reason",
    [
        ("notes.md", "NOT_ALLOWED_DIGEST"),
        ("TODO.md", "NOT_ALLOWED_DIGEST"),  # case matters
        ("todo.txt", "NOT_ALLOWED_DIGEST"),
        ("Inbox/todo.md", "NOT_ALLOWED_DIGEST"),  # root only
        ("../todo.md", "TRAVERSAL"),
        ("/todo.md", "ABSOLUTE"),
        ("C:todo.md", "DRIVE_OR_STREAM"),
        ("todo.md:hidden", "DRIVE_OR_STREAM"),
        ("todo.md\x00", "NULL_BYTE"),
        ("todo.md ", "BAD_COMPONENT"),
        ("", "EMPTY"),
        (None, "NOT_TEXT"),
    ],
)
def test_every_other_name_is_blocked(config, name, reason):
    with pytest.raises(SandboxViolation) as info:
        check_digest_path(config, name)
    assert info.value.reason == reason


def test_a_planted_shortcut_out_of_the_vault_is_blocked(config, vault, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    try:
        os.symlink(outside, vault / "todo.md")
    except OSError:
        pytest.skip("this machine cannot make symlinks")
    with pytest.raises(SandboxViolation) as info:
        check_digest_path(config, "todo.md")
    assert info.value.reason == "OUTSIDE_VAULT"
    assert outside.read_text(encoding="utf-8") == "secret"


def test_a_shortcut_into_a_zone_is_also_blocked(config, vault):
    note = vault / "Ideas" / "x.md"
    note.write_text("keep", encoding="utf-8")
    try:
        os.symlink(note, vault / "todo.md")
    except OSError:
        pytest.skip("this machine cannot make symlinks")
    with pytest.raises(SandboxViolation):
        check_digest_path(config, "todo.md")
    assert note.read_text(encoding="utf-8") == "keep"


def test_a_folder_named_todo_md_is_blocked(config, vault):
    (vault / "todo.md").mkdir()
    with pytest.raises(SandboxViolation) as info:
        check_digest_path(config, "todo.md")
    assert info.value.reason == "NOT_A_FILE"


# ---------- the writer ----------


def test_write_creates_then_overwrites(config, vault):
    assert write_digest(config, "todo.md", "first") == "todo.md"
    assert (vault / "todo.md").read_text(encoding="utf-8") == "first\n"
    write_digest(config, "todo.md", "second\r\nline")
    assert (vault / "todo.md").read_text(encoding="utf-8") == "second\nline\n"


def test_no_temp_files_are_left_behind(config, vault):
    write_digest(config, "daily_brief.md", "brief")
    write_digest(config, "daily_brief.md", "brief again")
    assert sorted(p.name for p in vault.iterdir() if p.is_file()) == ["daily_brief.md"]


@pytest.mark.parametrize(
    "content, reason",
    [("   ", "EMPTY_CONTENT"), ("x" * 100_001, "CONTENT_TOO_LARGE"), ("\ud800", "BAD_ENCODING")],
    ids=["empty", "too-large", "bad-encoding"],  # short ids: Windows folder names
)
def test_bad_content_is_rejected_and_old_file_is_kept(config, vault, content, reason):
    write_digest(config, "todo.md", "old")
    with pytest.raises(NoteError) as info:
        write_digest(config, "todo.md", content)
    assert info.value.reason == reason
    assert (vault / "todo.md").read_text(encoding="utf-8") == "old\n"


def test_a_crash_during_replace_keeps_the_old_file(config, vault, monkeypatch):
    write_digest(config, "todo.md", "old")

    def broken_replace(*_args):
        raise OSError("disk gone")

    monkeypatch.setattr(digest_module.os, "replace", broken_replace)
    with pytest.raises(OSError):
        write_digest(config, "todo.md", "new")
    assert (vault / "todo.md").read_text(encoding="utf-8") == "old\n"
    assert [p.name for p in vault.iterdir() if p.is_file()] == ["todo.md"]


# ---------- through MCP ----------


def test_mcp_write_digest_works(vault, config):
    result = call(create_server(config), "write_digest", {"name": "todo.md", "content": "- [ ] a"})
    assert result.data == {"path": "todo.md"}
    assert (vault / "todo.md").read_text(encoding="utf-8") == "- [ ] a\n"


def test_mcp_write_digest_blocks_and_hides_the_path(vault, config):
    with pytest.raises(ToolError) as info:
        call(create_server(config), "write_digest", {"name": "../evil.md", "content": "x"})
    assert str(info.value) == "BLOCKED:TRAVERSAL"
    assert str(vault) not in str(info.value)


def test_write_note_still_cannot_reach_the_root(vault, config):
    with pytest.raises(ToolError) as info:
        call(create_server(config), "write_note", {"folder": "todo.md", "title": "x", "content": "y"})
    assert "BLOCKED:NOT_ALLOWED_DIR" in str(info.value)
