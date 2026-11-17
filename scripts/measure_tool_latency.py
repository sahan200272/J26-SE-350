"""Measure tool-call latency through the two real MCP servers (RP-16, section 4b).

Synthetic data only. No LLM. Not evaluation data. The calendar is the in-memory
fake, so real Google calls (network) are NOT measured here.

Run from the repo root:
    python -m scripts.measure_tool_latency
    python -m scripts.measure_tool_latency --plans 50 --warmup 3 --out latency.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta
from importlib.metadata import version
from pathlib import Path

from agentic_core.decoding.plan_schema import ActionPlan, PlannedEvent, PlannedNote
from agentic_core.mcp_servers.orchestrator import Orchestrator, stdio_targets

TARGET_MS = 1500.0  # NFR-01: under 1.5 seconds per tool call
FOLDERS = ("Inbox", "Meetings", "Ideas")


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def summarise(values: list[float]) -> dict[str, float]:
    return {
        "calls": len(values),
        "median_ms": statistics.median(values),
        "p95_ms": percentile(values, 95),
        "max_ms": max(values),
    }


def make_plan(i: int) -> ActionPlan:
    """One synthetic note (about 640 characters) and one synthetic event."""
    return ActionPlan(
        notes=[
            PlannedNote(
                title=f"Synthetic note {i}",
                body="Synthetic text for speed testing. " * 18,
                folder=FOLDERS[i % len(FOLDERS)],
            )
        ],
        events=[
            PlannedEvent(
                title=f"Synthetic event {i}",
                start=datetime(2026, 10, 19, 9, 0) + timedelta(minutes=30 * i),
                attendees=["Alice", "Bob"],
            )
        ],
    )


async def measure(vault: Path, plans: int, warmup: int) -> dict:
    fs_transport, cal_transport = stdio_targets(vault)
    samples: dict[str, list[float]] = {"write_note": [], "create_event": []}
    failures = 0

    started = time.perf_counter()
    async with Orchestrator(fs_transport, cal_transport) as orchestrator:
        connect_ms = (time.perf_counter() - started) * 1000.0
        for i in range(warmup + plans):
            report = await orchestrator.run_plan(make_plan(i))
            failures += len(report.failed)
            if i < warmup:
                continue  # warm-up plans are not counted
            for item in report.items:
                if item.status != "failed":
                    tool = "create_event" if item.kind == "event" else "write_note"
                    samples[tool].append(item.latency_ms)
    return {"connect_ms": connect_ms, "failures": failures, "samples": samples}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure MCP tool-call latency")
    parser.add_argument("--plans", type=int, default=50, help="measured plans (untuned guess)")
    parser.add_argument("--warmup", type=int, default=3, help="plans not counted (untuned guess)")
    parser.add_argument("--out", type=Path, default=None, help="also write the result as JSON")
    args = parser.parse_args(argv)
    if args.plans < 1 or args.warmup < 0:
        parser.error("--plans must be at least 1 and --warmup at least 0")

    with tempfile.TemporaryDirectory(prefix="vault-latency-", ignore_cleanup_errors=True) as folder:
        result = asyncio.run(measure(Path(folder), args.plans, args.warmup))

    summary = {tool: summarise(values) for tool, values in result["samples"].items() if values}
    slowest = max((s["max_ms"] for s in summary.values()), default=0.0)
    valid = result["failures"] == 0 and len(summary) == 2
    environment = {
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu_threads": os.cpu_count(),
        "fastmcp": version("fastmcp"),
    }

    print(f"Tool-call latency in ms: {args.plans} plans after {args.warmup} warm-up")
    print("Synthetic data, no LLM, calendar = in-memory fake (real Google calls NOT measured)")
    print(f"{'tool':<14}{'calls':>7}{'median':>10}{'p95':>10}{'max':>10}")
    for tool, stats in summary.items():
        print(
            f"{tool:<14}{stats['calls']:>7}{stats['median_ms']:>10.1f}"
            f"{stats['p95_ms']:>10.1f}{stats['max_ms']:>10.1f}"
        )
    print(f"Server start (connect to both): {result['connect_ms']:.0f} ms (one time)")
    print(f"Environment: {environment}")
    if not valid:
        print(f"INVALID RUN: {result['failures']} call(s) failed. Do not use these numbers.")
    else:
        verdict = "PASS" if slowest < TARGET_MS else "FAIL"
        print(f"NFR-01 target (< {TARGET_MS:.0f} ms per call), slowest call {slowest:.1f} ms: {verdict}")

    if args.out is not None:
        payload = {
            "measured_at": datetime.now().isoformat(timespec="seconds"),
            "plans": args.plans,
            "warmup": args.warmup,
            "valid": valid,
            "connect_ms": result["connect_ms"],
            "failures": result["failures"],
            "summary": summary,
            "environment": environment,
            "note": "synthetic data, no LLM, in-memory calendar; Google calls not measured",
        }
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved: {args.out}")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())