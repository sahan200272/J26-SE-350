"""Escape test for the write_digest tool (RP-18, section 1).

The frozen 50 vectors (RP-16) target write_note and stay unchanged.
These 12 extra vectors target the new write_digest tool through real MCP.
For each one: build a fresh vault plus a canary outside it, send the vector
as `name`, then check that nothing changed anywhere except the two allowed
root files. Any other change counts as an escape.
"""

import asyncio
import os
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from agentic_core.mcp_servers.filesystem_server.sandbox import SandboxConfig
from agentic_core.mcp_servers.filesystem_server.server import create_server

DIGEST_VECTORS = [
    ("D01", "../todo.md"),
    ("D02", "../../outside/canary.txt"),
    ("D03", "..\\todo.md"),
    ("D04", "/etc/passwd"),
    ("D05", "C:\\Windows\\win.ini"),
    ("D06", "todo.md\x00.txt"),
    ("D07", "Inbox/../todo.md"),
    ("D08", "./todo.md"),
    ("D09", "todo.md::$DATA"),
    ("D10", "%2e%2e%2ftodo.md"),
    ("D11", "CON.md"),
    ("D12", "todo.md/"),
]

ALLOWED = {"todo.md", "daily_brief.md"}


def _snapshot(world: Path) -> dict[str, tuple]:
    items = {}
    for dirpath, dirnames, filenames in os.walk(world, followlinks=False):
        for name in dirnames + filenames:
            full = Path(dirpath) / name
            rel = os.path.relpath(full, world)
            info = full.lstat()
            items[rel] = (info.st_mode, info.st_size, info.st_mtime_ns)
    return items


@pytest.mark.parametrize("vector_id, vector", DIGEST_VECTORS, ids=[v[0] for v in DIGEST_VECTORS])
def test_digest_vector_cannot_escape(tmp_path, vector_id, vector):
    world = tmp_path / "world"
    vault = world / "vault"
    for zone in ("Inbox", "Meetings", "Ideas"):
        (vault / zone).mkdir(parents=True)
    (world / "outside").mkdir()
    (world / "outside" / "canary.txt").write_text("untouched", encoding="utf-8")

    before = _snapshot(world)

    async def run():
        async with Client(create_server(SandboxConfig(vault_root=vault))) as client:
            return await client.call_tool("write_digest", {"name": vector, "content": "probe"})

    with pytest.raises(ToolError) as info:
        asyncio.run(run())
    assert str(info.value).startswith(("BLOCKED:", "REJECTED:"))

    after = _snapshot(world)
    changed = {k for k in after if before.get(k) != after[k]} | {k for k in before if k not in after}
    allowed = {os.path.join("vault", name) for name in ALLOWED}
    assert changed <= allowed, f"{vector_id} escaped: {sorted(changed)}"
    assert not changed, f"{vector_id} wrote a file although it was blocked"
