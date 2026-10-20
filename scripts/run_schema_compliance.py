"""Run the frozen 200 schema-compliance cases against the local LLM (NFR-04).

Definition: docs/evaluation/schema_compliance_definition.md
The first full official run is the result. Never tune on these 200 cases.

Run from the repo root:
    python -m scripts.run_schema_compliance --out docs/evaluation/<name>.json
    python -m scripts.run_schema_compliance --mode baseline --out ...   (grammar off, comparison only)
    python -m scripts.run_schema_compliance --dataset agentic_core/datasets/schema_compliance/dev_cases.json

Exit code: 0 = grammar mode, all cases ran, rate >= 98% (baseline: all cases ran),
1 = below target, not all cases ran, or Ollama not ready,
2 = the dataset or the frozen setup was changed (the result would not be official).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from agentic_core.tests.schema_compliance import frozen_setup
from agentic_core.tests.schema_compliance.cases import EVAL_PATH, fingerprint, load_cases
from agentic_core.tests.schema_compliance.harness import (
    MODES,
    TARGET_RATE,
    RecordingClient,
    run_cases,
    setup_hashes,
    summarize,
)
from agentic_core.tests.schema_compliance.test_case_dataset import FROZEN_FINGERPRINT

NOT_CHECKED = "not checked"
_PLACEMENT = re.compile(r"\d+%/\d+% CPU/GPU|100% GPU|100% CPU")


def _command(args: list[str]) -> str | None:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def model_placement(model: str) -> dict[str, str]:
    """Where Ollama put the model, from 'ollama ps'. Only meaningful while the model is loaded."""
    out = _command(["ollama", "ps"])
    if out is None:
        return {"placement": NOT_CHECKED, "line": NOT_CHECKED}
    for line in out.splitlines():
        if line.split() and line.split()[0] == model:
            match = _PLACEMENT.search(line)
            return {"placement": match.group(0) if match else NOT_CHECKED, "line": " ".join(line.split())}
    return {"placement": NOT_CHECKED, "line": "model not listed by ollama ps"}


def machine_info() -> dict[str, Any]:
    gpu = _command(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader"])
    ollama_server = _command(["ollama", "--version"])

    def package(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return NOT_CHECKED

    return {
        "gpu": gpu.splitlines()[0] if gpu else NOT_CHECKED,
        "ollama_server": ollama_server or NOT_CHECKED,
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu_threads": os.cpu_count(),
        "packages": {p: package(p) for p in ("ollama", "pydantic", "fastmcp")},
    }


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.1f}%"


def _print_summary(summary: dict[str, Any]) -> None:
    head = f"{'category':<15}{'run':>5}{'ok':>5}{'json':>6}{'schema':>8}{'cutoff':>8}{'infra':>7}{'rate':>8}  95% CI"
    print(head)
    rows = list(summary["by_category"].items()) + [("TOTAL", summary["total"])]
    for name, s in rows:
        print(f"{name:<15}{s['cases_run']:>5}{s['compliant']:>5}{s['json_valid']:>6}{s['schema_valid']:>8}"
              f"{s['cut_off']:>8}{s['infra_errors']:>7}{_percent(s['rate']):>8}  "
              f"{_percent(s['ci95_low'])} to {_percent(s['ci95_high'])}")


def main(argv: list[str] | None = None, client: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Run the JSON schema-compliance test (NFR-04)")
    parser.add_argument("--dataset", type=Path, default=EVAL_PATH, help="case file (JSON)")
    parser.add_argument("--mode", choices=MODES, default="grammar",
                        help="grammar = official target; baseline = grammar off, comparison only")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases (never official)")
    parser.add_argument("--out", type=Path, default=None, help="also write the result as JSON")
    args = parser.parse_args(argv)

    cases = load_cases(args.dataset)
    fp = fingerprint(cases)
    is_eval = args.dataset.resolve() == EVAL_PATH.resolve()
    if is_eval and fp != FROZEN_FINGERPRINT:
        print("DATASET CHANGED AFTER IT WAS FROZEN. This result would not be official. Stopping.")
        return 2

    hashes = setup_hashes()
    frozen = frozen_setup.FROZEN_SETUP_HASHES
    if is_eval and frozen is not None and hashes != frozen:
        changed = sorted(k for k in hashes if hashes.get(k) != frozen.get(k))
        print(f"FROZEN SETUP CHANGED ({', '.join(changed)}). This result would not be official. Stopping.")
        return 2

    if args.limit is not None:
        cases = cases[: args.limit]
    official = is_eval and args.limit is None and frozen is not None

    if client is None:
        from agentic_core.llm.client import LLMClient

        client = LLMClient()
        if not client.is_ready():
            print("Ollama is not running or the model is missing. Nothing was run.")
            return 1
    recorder = RecordingClient(client, args.mode)
    model = client.config.model
    placement_first: dict[str, str] = {"placement": NOT_CHECKED, "line": NOT_CHECKED}

    print(f"Schema compliance: {len(cases)} cases, mode={args.mode}, model={model}, "
          f"{'OFFICIAL' if official else 'NOT OFFICIAL'}")
    started_at = datetime.now()

    def progress(index: int, record: dict) -> None:
        nonlocal placement_first
        if index == 1:
            placement_first = model_placement(model)
            print(f"Model placement after case 1: {placement_first['placement']}")
        if record["status"] == "infra_error":
            verdict = "INFRA ERROR " + record["infra_error"]
        else:
            verdict = "ok" if record["compliant"] else "NOT COMPLIANT " + ",".join(record["error_types"])
            verdict += f"  tokens={record['tokens_out']} {record['llm_total_s']:.1f}s"
        elapsed = (datetime.now() - started_at).total_seconds()
        left = elapsed / index * (len(cases) - index)
        print(f"[{index:>3}/{len(cases)}] {record['id']} {record['category']:<13} {verdict}  "
              f"(about {left / 60:.0f} min left)", flush=True)

    records, interrupted = run_cases(cases, recorder, progress)
    finished_at = datetime.now()
    placement_end = model_placement(model)

    summary = summarize(records)
    total = summary["total"]
    all_run = not interrupted and len(records) == len(cases) and total["infra_errors"] == 0
    official = official and all_run

    print()
    _print_summary(summary)
    if interrupted:
        print(f"STOPPED EARLY: {len(records)} of {len(cases)} cases ran. Not a complete result.")
    if total["extractor_disagrees"]:
        print(f"WARNING: extract_plan disagreed with the check on {total['extractor_disagrees']} case(s).")
    print(f"Compliance: {total['compliant']}/{total['cases_run']} = {_percent(total['rate'])}  "
          f"(95% CI {_percent(total['ci95_low'])} to {_percent(total['ci95_high'])}, "
          f"target >= {100 * TARGET_RATE:.0f}%, mode={args.mode})")
    print("Dataset fingerprint:", fp)
    print("Status:", "OFFICIAL" if official else "NOT OFFICIAL")
    machine = machine_info()
    print(f"Machine: {machine['gpu']}; placement at end: {placement_end['placement']}")

    if args.out is not None:
        payload = {
            "measured_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "official": official,
            "mode": args.mode,
            "target": f">= {100 * TARGET_RATE:.0f}% (grammar mode only)",
            "definition": "docs/evaluation/schema_compliance_definition.md",
            "dataset": args.dataset.as_posix(),
            "dataset_fingerprint": fp,
            "cases": len(cases),
            "cases_run": total["cases_run"],
            "all_run": all_run,
            "interrupted": interrupted,
            "limit": args.limit,
            "setup_hashes": hashes,
            "setup_frozen": frozen is not None,
            "model": model,
            "llm_options": {"num_ctx": client.config.num_ctx, "temperature": client.config.temperature,
                            "num_predict": client.config.num_predict},
            "model_placement_after_first_case": placement_first,
            "model_placement_at_end": placement_end,
            "machine": machine,
            "summary": summary,
            "records": records,
            "note": "prefilter off; first answer only; no retry; JSON-RPC envelope not measured",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved: {args.out}")

    if not all_run:
        return 1
    if args.mode == "grammar":
        return 0 if total["rate"] >= TARGET_RATE else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
