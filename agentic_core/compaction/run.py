"""Nightly compaction entry point (RP-18, section 3).

A plain Python program. The scheduler (cron on the hub, Task Scheduler on
Windows) only starts it; all logic is here, so it can be tested anywhere.

    python -m agentic_core.compaction.run --vault <vault folder>
    python -m agentic_core.compaction.run --vault <vault> --dry-run
    python -m agentic_core.compaction.run --vault <vault> --now 2026-11-17T20:00

Steps: read the vault (read only, through the sandbox guard), apply the
rules (no LLM), then write todo.md and daily_brief.md ONLY through the
filesystem MCP server's write_digest tool (a separate process over stdio).

Exit codes: 0 both files written, 1 a write failed, 2 bad input or settings.
The log holds counts and reason codes only, never note text.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.exceptions import ToolError

from agentic_core.mcp_servers.orchestrator import REPO_ROOT, _safe_code

from .collect import collect
from .config import CONFIG_PATH, CompactionConfig, load_config
from .render import render_brief, render_todo
from .rules import Digest, build_digest

logger = logging.getLogger("agentic_core.compaction")

TODO_NAME = "todo.md"
BRIEF_NAME = "daily_brief.md"


@dataclass(frozen=True)
class WriteResult:
    name: str
    ok: bool
    code: str | None
    latency_ms: float


def compact(vault: Path, config: CompactionConfig, now: datetime) -> tuple[Digest, str, str]:
    """Read and apply the rules. Pure: writes nothing."""
    result = collect(vault, config, now)
    digest = build_digest(list(result.notes), config, now, result.skipped)
    return digest, render_todo(digest, config), render_brief(digest, config)


def filesystem_target(vault: Path) -> Any:
    """The real filesystem MCP server as a separate process (same as the orchestrator)."""
    from fastmcp.client.transports import StdioTransport

    return StdioTransport(
        command=sys.executable,
        args=["-m", "agentic_core.mcp_servers.filesystem_server.server", "--vault", str(vault)],
        cwd=str(REPO_ROOT),
    )


async def write_digests(target: Any, files: dict[str, str]) -> list[WriteResult]:
    results: list[WriteResult] = []
    try:
        async with Client(target) as client:
            for name, content in files.items():
                started = time.perf_counter()
                code: str | None = None
                try:
                    data = (await client.call_tool("write_digest", {"name": name, "content": content})).data
                    if not (isinstance(data, dict) and data.get("path") == name):
                        code = "BAD_RESPONSE"
                except ToolError as error:
                    code = _safe_code(str(error))
                except Exception as error:  # connection lost, timeout, ...
                    logger.error("write_digest failed: %s", type(error).__name__)
                    code = "TRANSPORT_ERROR"
                ms = (time.perf_counter() - started) * 1000.0
                results.append(WriteResult(name, code is None, code, ms))
    except Exception as error:
        logger.error("cannot connect to the filesystem server: %s", type(error).__name__)
        done = {r.name for r in results}
        results += [WriteResult(n, False, "CONNECT_FAILED", 0.0) for n in files if n not in done]
    return results


def _parse_now(text: str | None, config: CompactionConfig) -> datetime:
    if text is None:
        return datetime.now(config.zone)
    moment = datetime.fromisoformat(text)
    return moment.replace(tzinfo=config.zone) if moment.tzinfo is None else moment


def _setup_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )


def main(argv: list[str] | None = None, *, target: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Nightly compaction: todo.md and daily_brief.md")
    parser.add_argument("--vault", required=True, type=Path, help="path to the vault folder")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="settings file")
    parser.add_argument("--now", default=None, help="pretend time, e.g. 2026-11-17T20:00 (tests)")
    parser.add_argument("--dry-run", action="store_true", help="print the files, write nothing")
    parser.add_argument("--log-file", type=Path, default=None, help="also write the log here")
    args = parser.parse_args(argv)

    _setup_logging(args.log_file)
    vault = args.vault.expanduser().resolve()
    if not vault.is_dir():
        logger.error("the vault folder does not exist")
        return 2
    try:
        config = load_config(args.config)
        now = _parse_now(args.now, config)
    except (OSError, ValueError) as error:
        logger.error("bad settings: %s", error)
        return 2

    started = time.perf_counter()
    digest, todo, brief = compact(vault, config, now)
    compact_ms = (time.perf_counter() - started) * 1000.0
    logger.info(
        "compaction: %d new note(s), %d open task(s), %d done, %d event(s), skipped=%s, %.0f ms",
        len(digest.new_notes),
        len(digest.open_tasks),
        len(digest.done_today),
        len(digest.events),
        digest.skipped,
        compact_ms,
    )

    if args.dry_run:
        sys.stdout.write(f"===== {TODO_NAME} =====\n{todo}\n===== {BRIEF_NAME} =====\n{brief}\n")
        return 0

    results = asyncio.run(
        write_digests(target or filesystem_target(vault), {TODO_NAME: todo, BRIEF_NAME: brief})
    )
    for result in results:
        if result.ok:
            logger.info("wrote %s (%.1f ms)", result.name, result.latency_ms)
        else:
            logger.error("could not write %s: %s", result.name, result.code)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
