"""Run the frozen 50 path-traversal vectors against the filesystem MCP server (RP-16, 4c).

The first full run on the real machine is the official result. Fixes made after
a failing run must be reported as "after fix, not independent".

Run from the repo root:
    python -m scripts.run_path_traversal_suite --out path_traversal_results.json

Exit code: 0 = no escape, 1 = at least one escape, 2 = the dataset was changed
after it was frozen (the result is not official).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from agentic_core.tests.adversarial_fuzzing.suite import run_suite
from agentic_core.tests.adversarial_fuzzing.test_vector_dataset import FROZEN_FINGERPRINT
from agentic_core.tests.adversarial_fuzzing.vectors import DATASET_PATH, fingerprint, load_vectors

VERDICTS = ("blocked", "rejected", "harmless", "escape", "error", "not_run")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the path-traversal escape test")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH, help="vector file (JSON)")
    parser.add_argument("--out", type=Path, default=None, help="also write the result as JSON")
    args = parser.parse_args(argv)

    vectors = load_vectors(args.dataset)
    fp = fingerprint(vectors)
    official = args.dataset == DATASET_PATH and fp == FROZEN_FINGERPRINT
    if args.dataset == DATASET_PATH and not official:
        print("DATASET CHANGED AFTER IT WAS FROZEN. This result is not official. Stopping.")
        return 2

    with tempfile.TemporaryDirectory(prefix="pt-suite-", ignore_cleanup_errors=True) as folder:
        result = run_suite(vectors, Path(folder))

    categories = sorted({o.category for o in result.outcomes})
    print(f"Path-traversal escape test: {len(vectors)} vectors, "
          f"{len(result.outcomes)} attempts (folder and title positions)")
    print("MCP transport: in-process (the real stdio path is tested separately)")
    print(f"{'category':<20}" + "".join(f"{v:>10}" for v in VERDICTS))
    for category in categories:
        row = [o.verdict for o in result.outcomes if o.category == category]
        print(f"{category:<20}" + "".join(f"{row.count(v):>10}" for v in VERDICTS))
    totals = result.counts()
    print(f"{'TOTAL':<20}" + "".join(f"{totals.get(v, 0):>10}" for v in VERDICTS))

    escaped = result.escaped_ids
    run = result.vectors_run
    print(f"Vectors run: {run} of {len(vectors)}"
          + ("  (WARNING: some could not be set up, see not_run)" if run < len(vectors) else ""))
    print(f"Sandbox escape rate: {len(escaped)}/{run} = {100 * result.escape_rate:.1f}%"
          f"  (target 0.0%)")
    for outcome in result.outcomes:
        if outcome.verdict in ("escape", "error"):
            print(f"  {outcome.verdict.upper()} {outcome.vector_id} [{outcome.position}] "
                  f"{outcome.detail} {' '.join(outcome.evidence)}")
    print("Dataset fingerprint:", fp)
    print("Status:", "OFFICIAL (frozen dataset)" if official else "NOT OFFICIAL (custom dataset)")
    environment = {"python": platform.python_version(), "os": platform.platform(),
                   "fastmcp": version("fastmcp"), "cpu_threads": os.cpu_count()}
    print("Environment:", environment)

    if args.out is not None:
        payload = {
            "measured_at": datetime.now().isoformat(timespec="seconds"),
            "official": official,
            "dataset_fingerprint": fp,
            "vectors": len(vectors),
            "vectors_run": run,
            "escaped_vector_ids": escaped,
            "escape_rate": result.escape_rate,
            "totals": totals,
            "outcomes": [
                {"id": o.vector_id, "category": o.category, "position": o.position,
                 "verdict": o.verdict, "detail": o.detail, "evidence": list(o.evidence)}
                for o in result.outcomes
            ],
            "environment": environment,
            "note": "in-process MCP transport; first full run is the official result",
        }
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved: {args.out}")
    return 1 if escaped else 0


if __name__ == "__main__":
    sys.exit(main())