"""PP1 demo: one transcript through Stage 1 and Stage 2 of the Agentic Reasoning Core.

    transcript -> segments -> prefilter -> constrained LLM plan (Stage 1)
               -> orchestrator -> filesystem + calendar MCP servers (Stage 2)

Real parts: the local LLM (Ollama), the schema check, the filesystem MCP server
and the sandbox guard. The calendar is the in-memory fake (Google backend not
built). Nothing leaves this computer. This is a demo, not an evaluation run:
it writes no result file and its numbers never count toward a target.

The same run_pipeline() is used by this command and by the panel's
"Run the pipeline" page, so both always show the same steps.

Run from the repo root:
    python -m scripts.demo_pipeline <transcript.md> --vault <folder>
    python -m scripts.demo_pipeline <transcript.md> --vault <folder> --attack

--attack also sends a few path-traversal attempts straight to the filesystem
server, the way a confused or tricked model might, and shows what happens.
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import statistics
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from fastmcp import Client
from fastmcp.exceptions import ToolError

from agentic_core.decoding.extractor import extract_plan
from agentic_core.decoding.plan_schema import ActionPlan
from agentic_core.llm.client import LLMClient
from agentic_core.mcp_servers.orchestrator import Orchestrator, stdio_targets
from agentic_core.segmentation.segmenter import segment_transcript
from agentic_core.segmentation.transcript import parse_transcript

# Attempts a tricked model might send. Each one must come back BLOCKED.
ATTACKS = (
    "../../Windows/System32",
    "Inbox/../../outside_the_vault",
    "C:/Windows/System32",
    "Meetings/../../../etc",
)

LINE = "-" * 72


def recording_date(started_at: str | None, given: str | None) -> date:
    """The day of the recording: the given date wins, else the transcript header."""
    if given:
        return date.fromisoformat(given)
    if started_at:
        return datetime.fromisoformat(started_at).date()
    raise ValueError("No recording date: give a date (the transcript has no started_at).")


def describe_machine() -> str:
    """OS plus the NVIDIA GPU name and memory when the driver can be asked."""
    text = platform.platform()
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            name = name.decode() if isinstance(name, bytes) else name
            total_mb = pynvml.nvmlDeviceGetMemoryInfo(handle).total / 1024**2
            text += f", {name} {total_mb / 1024:.0f} GB"
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        text += ", no NVIDIA GPU found"
    return text


def model_placement(client) -> str:
    """Where Ollama holds the model now, e.g. '56% CPU / 44% GPU'."""
    try:
        for m in client._client.ps().models:
            if m.model == client.config.model and m.size:
                gpu = round(100 * (m.size_vram or 0) / m.size)
                return "100% GPU" if gpu >= 100 else f"{100 - gpu}% CPU / {gpu}% GPU"
    except Exception:
        pass
    return "placement unknown"


async def _run_tools(vault: Path, plan: ActionPlan, attack: bool, say: Callable[[str], None]) -> dict:
    say("\n" + LINE)
    say("STAGE 2  FastMCP sandboxed tools (servers run as separate processes over stdio)")
    say(f"Vault: {vault}")
    say("Calendar: in-memory fake (Google backend not built). No invitation is sent.")
    say(LINE)

    fs_target, cal_target = stdio_targets(vault)
    started = time.perf_counter()
    async with Orchestrator(fs_target, cal_target) as orchestrator:
        connect_ms = (time.perf_counter() - started) * 1000
        say(f"Both MCP servers started in {connect_ms:.0f} ms (one time).")
        report = await orchestrator.run_plan(plan)

    calls = []
    if not report.items:
        say("The plan was empty: nothing to write.")
    for item in report.items:
        tool = "write_note" if item.kind == "note" else "create_event"
        calls.append({"tool": tool, "index": item.index, "status": item.status,
                      "code": item.code, "reference": item.reference,
                      "ms": round(item.latency_ms, 1)})
        if item.status == "failed":
            say(f"  {tool:<12} #{item.index}: FAILED {item.code} ({item.latency_ms:.1f} ms)")
        else:
            say(f"  {tool:<12} #{item.index}: {item.status.upper():<7} {item.reference} "
                f"({item.latency_ms:.1f} ms)")

    attacks = []
    if attack:
        say("\nAttack check: path-traversal attempts sent straight to write_note")
        fs_only, _ = stdio_targets(vault)
        async with Client(fs_only) as filesystem:
            for folder in ATTACKS:
                try:
                    result = await filesystem.call_tool(
                        "write_note", {"folder": folder, "title": "attack", "content": "x"}
                    )
                except ToolError as error:
                    attacks.append({"folder": folder, "blocked": True, "code": str(error)})
                    say(f"  BLOCKED      folder={folder!r:<36} -> {error}")
                else:
                    attacks.append({"folder": folder, "blocked": False, "code": str(result.data)})
                    say(f"  NOT BLOCKED  folder={folder!r:<36} -> wrote {result.data}")
    return {"connect_ms": round(connect_ms), "calls": calls, "attacks": attacks}


def run_pipeline(
    text: str,
    name: str,
    vault: Path,
    client,
    *,
    date_text: str | None = None,
    attack: bool = False,
    say: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run Stage 1 and Stage 2 on one transcript. Returns everything the UI needs.

    Raises TranscriptFormatError or ValueError for a bad transcript or date.
    """
    log: list[str] = []

    def emit(line: str = "") -> None:
        log.append(line)
        say(line)

    transcript = parse_transcript(text)
    reference = recording_date(transcript.started_at, date_text)
    segments = segment_transcript(transcript)
    vault.mkdir(parents=True, exist_ok=True)

    emit(LINE)
    emit(f"STAGE 1  Constrained decoding   model={client.config.model}  "
         f"temperature={client.config.temperature}  num_ctx={client.config.num_ctx}")
    emit(f"Transcript: {name} | {len(transcript.turns)} turns | "
         f"{len(segments)} segments | recording date {reference.isoformat()}")
    emit(LINE)

    notes, events, tpots, seg_rows = [], [], [], []
    for segment in segments:
        lines = segment.to_text().splitlines()
        emit(f"\n[Segment {segment.index}] {len(segment.turns)} turns, "
             f"started_because={segment.started_because}")
        for line in lines:
            emit(f"    {line}")

        result = extract_plan(segment, client, reference)
        row = {"index": segment.index, "started_because": segment.started_because,
               "lines": lines, "status": "skipped", "tokens": 0, "ms_per_token": None,
               "seconds": None, "error": None, "plan": None}
        if result.skipped:
            emit("  -> Prefilter: no task, time or idea words. Skipped, no LLM call.")
            seg_rows.append(row)
            continue

        row.update(tokens=result.tokens_out, ms_per_token=round(result.tpot_ms, 1),
                   seconds=round(result.total_s, 1))
        if result.tokens_out:
            tpots.append(result.tpot_ms)
        emit(f"  -> LLM: {result.tokens_out} tokens, {result.tpot_ms:.0f} ms/token, "
             f"{result.total_s:.1f} s")
        if result.plan is None:
            row.update(status="invalid", error=result.error)
            emit(f"  -> INVALID first-try answer (reported, not repaired): {result.error}")
        else:
            row.update(status="valid", plan=result.plan.model_dump(mode="json"))
            emit("  -> Valid JSON, passed the Pydantic schema. Plan:")
            for line in result.plan.model_dump_json(indent=2).splitlines():
                emit(f"       {line}")
            notes.extend(result.plan.notes)
            events.extend(result.plan.events)
        seg_rows.append(row)

    llm_calls = sum(1 for r in seg_rows if r["status"] != "skipped")
    valid = sum(1 for r in seg_rows if r["status"] == "valid")
    skipped = sum(1 for r in seg_rows if r["status"] == "skipped")
    emit(f"\nStage 1 result: {llm_calls} LLM call(s), {valid} valid on first try, "
         f"{skipped} segment(s) skipped by prefilter.")
    emit("(Demo only. The official schema-compliance target needs the 200-case run.)")

    placement = model_placement(client)
    tools = asyncio.run(_run_tools(vault, ActionPlan(notes=notes, events=events), attack, emit))

    calls, attacks = tools["calls"], tools["attacks"]
    failed = sum(1 for c in calls if c["status"] == "failed")
    blocked = sum(1 for a in attacks if a["blocked"])
    ok = failed == 0 and blocked == len(attacks) and valid == llm_calls

    emit("\n" + LINE)
    emit(f"Done. The vault now holds {len(list(vault.rglob('*.md')))} .md file(s).")
    emit(f"Model placement during this run: {placement}.")
    emit("Everything ran on this computer. " + ("All steps OK." if ok else "Some steps FAILED (see above)."))

    return {
        "name": name,
        "recording_date": reference.isoformat(),
        "turns": len(transcript.turns),
        "model": client.config.model,
        "machine": describe_machine(),
        "placement": placement,
        "vault": str(vault),
        "segments": seg_rows,
        "connect_ms": tools["connect_ms"],
        "calls": calls,
        "attacks": attacks,
        "summary": {
            "segments": len(seg_rows),
            "skipped": skipped,
            "llm_calls": llm_calls,
            "valid_first_try": valid,
            "mean_ms_per_token": round(statistics.mean(tpots), 1) if tpots else None,
            "notes_written": sum(1 for c in calls if c["status"] == "written"),
            "events_created": sum(1 for c in calls if c["status"] == "created"),
            "events_existing": sum(1 for c in calls if c["status"] == "exists"),
            "tool_failures": failed,
            "slowest_tool_ms": max((c["ms"] for c in calls), default=None),
            "attacks_tried": len(attacks),
            "attacks_blocked": blocked,
        },
        "ok": ok,
        "log": "\n".join(log),
    }


def main(argv: list[str] | None = None, client=None) -> int:
    parser = argparse.ArgumentParser(description="PP1 demo of Stage 1 and Stage 2")
    parser.add_argument("transcript", type=Path, help="diarized Markdown transcript")
    parser.add_argument("--vault", type=Path, required=True, help="demo vault folder (created if missing)")
    parser.add_argument("--date", default=None, help="recording date YYYY-MM-DD (default: transcript header)")
    parser.add_argument("--attack", action="store_true", help="also try path-traversal attacks")
    args = parser.parse_args(argv)

    client = client or LLMClient()
    if not client.is_ready():
        print("Ollama is not running or the model is missing. Start Ollama first.")
        return 2

    text = args.transcript.read_text(encoding="utf-8-sig")
    try:
        result = run_pipeline(text, args.transcript.name, args.vault.expanduser().resolve(),
                              client, date_text=args.date, attack=args.attack)
    except ValueError as error:  # bad transcript or date
        print(f"error: {error}")
        return 2
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
