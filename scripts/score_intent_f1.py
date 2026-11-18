"""Score intent F1 offline from a frozen schema-compliance run (RP-17).

Definition: docs/evaluation/intent_f1_definition.md (agreed before any scoring).
No LLM call: the model's answers are read from the run's `raw_output` fields.
The first official score is the result. Never tune on these 200 cases.

Run from the repo root:
    python -m scripts.score_intent_f1 --out docs/evaluation/intent_f1_official.json
    python -m scripts.score_intent_f1 --run docs/evaluation/<other run>.json   (comparison)
    python -m scripts.score_intent_f1 --dataset <dev cases> --run <dev run>   (never official)

Exit code: 0 = official and F1 >= 90%, 1 = below target or not official,
2 = the run or the dataset cannot be scored (NOT MEASURED).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from agentic_core.segmentation.transcript import parse_transcript
from agentic_core.tests.intent_f1.scorer import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    STOP_WORDS,
    TARGET_F1,
    THRESHOLD,
    check_run,
    expected_plan,
    predicted_plan,
    score_case,
    summarize,
)
from agentic_core.tests.schema_compliance.cases import (
    EVAL_PATH,
    fingerprint,
    load_cases,
    recording_date,
)
from agentic_core.tests.schema_compliance.test_case_dataset import FROZEN_FINGERPRINT

OFFICIAL_RUN = Path("docs/evaluation/schema_compliance_official.json")


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.1f}%"


def score_run(cases: list[dict], run: dict) -> tuple[list[dict], list[dict], int]:
    """Score every case. Returns (scored cases, json records, compliance disagreements)."""
    by_id = {r["id"]: r for r in run["records"]}
    scored, records, disagreements = [], [], 0
    for case in cases:
        reference = recording_date(parse_transcript(case["transcript"]).started_at)
        record = by_id[case["id"]]
        expected = expected_plan(case["expected"], reference)
        predicted, compliant = predicted_plan(record.get("raw_output"), reference)
        if compliant != record.get("compliant"):
            disagreements += 1
        s = score_case(expected, predicted)
        scored.append({"id": case["id"], "category": case["category"],
                       "compliant": compliant, "score": s})
        records.append({"id": case["id"], "category": case["category"], "compliant": compliant,
                        "tp": s.tp, "fp": s.fp, "fn": s.fn,
                        "misses": s.misses, "extras": s.extras})
    return scored, records, disagreements


def _print_summary(summary: dict[str, Any]) -> None:
    print(f"{'category':<15}{'cases':>6}{'TP':>5}{'FP':>5}{'FN':>5}"
          f"{'precision':>11}{'recall':>8}{'F1':>8}{'exact':>7}")
    rows = [(k, v) for k, v in summary["by_category"].items() if k != "noise"]
    rows.append(("TOTAL", summary["total"]))
    for name, s in rows:
        print(f"{name:<15}{s['cases']:>6}{s['tp']:>5}{s['fp']:>5}{s['fn']:>5}"
              f"{_percent(s['precision']):>11}{_percent(s['recall']):>8}{_percent(s['f1']):>8}"
              f"{s['exact_cases']:>7}")
    noise = summary["by_category"].get("noise")
    if noise:
        print(f"noise: {noise['cases']} cases, {noise['fp']} extra items, "
              f"clean {noise['clean_cases']}/{noise['cases']} = {_percent(noise['clean_case_rate'])}")
    print(f"notes only F1 {_percent(summary['notes_only']['f1'])}, "
          f"events only F1 {_percent(summary['events_only']['f1'])}")
    nc = summary["non_compliant"]
    print(f"non-compliant cases: {nc['cases']} (they cause {nc['fn_from_them']} misses)")
    print(f"folder correct on matched notes: {summary['folder_accuracy']['correct']}/"
          f"{summary['folder_accuracy']['checked']}; attendees correct on matched events: "
          f"{summary['attendees_accuracy']['correct']}/{summary['attendees_accuracy']['checked']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score intent F1 from a frozen run (RP-17)")
    parser.add_argument("--run", type=Path, default=OFFICIAL_RUN, help="schema-compliance run (JSON)")
    parser.add_argument("--dataset", type=Path, default=EVAL_PATH, help="case file (JSON)")
    parser.add_argument("--out", type=Path, default=None, help="also write the result as JSON")
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES,
                        help="bootstrap resamples (only the default is official)")
    args = parser.parse_args(argv)

    cases = load_cases(args.dataset)
    dataset_fp = fingerprint(cases)
    is_eval = args.dataset.resolve() == EVAL_PATH.resolve()
    required_fp = FROZEN_FINGERPRINT if is_eval else dataset_fp
    run = json.loads(args.run.read_text(encoding="utf-8"))

    problems = check_run(run, cases, required_fp, dataset_fp)
    if problems:
        print("NOT MEASURED: " + "; ".join(problems))
        return 2

    scored, records, disagreements = score_run(cases, run)
    summary = summarize(scored, args.resamples)
    official = (is_eval and args.resamples == BOOTSTRAP_RESAMPLES and disagreements == 0
                and run.get("mode") == "grammar")
    total = summary["total"]

    print(f"Intent F1: {len(cases)} cases from {args.run.as_posix()} "
          f"(mode={run.get('mode')}, model={run.get('model')}), "
          f"{'OFFICIAL' if official else 'NOT OFFICIAL'}")
    print()
    _print_summary(summary)
    if disagreements:
        print(f"WARNING: compliance check disagrees with the run on {disagreements} case(s).")
    print(f"Micro F1: {_percent(total['f1'])} (95% CI {_percent(total['ci95_low'])} to "
          f"{_percent(total['ci95_high'])}, target >= {100 * TARGET_F1:.0f}%) -> {summary['result']}")

    if args.out is not None:
        payload = {
            "scored_at": datetime.now().isoformat(timespec="seconds"),
            "official": official,
            "target": f">= {100 * TARGET_F1:.0f}% micro F1",
            "definition": "docs/evaluation/intent_f1_definition.md",
            "dataset": args.dataset.as_posix(),
            "dataset_fingerprint": dataset_fp,
            "source_run": {
                "path": args.run.as_posix(),
                "measured_at": run.get("measured_at"),
                "mode": run.get("mode"),
                "model": run.get("model"),
                "llm_options": run.get("llm_options"),
                "setup_hashes": run.get("setup_hashes"),
                "machine_gpu": run.get("machine", {}).get("gpu"),
            },
            "scorer": {"threshold": THRESHOLD, "stop_words": sorted(STOP_WORDS),
                       "bootstrap_resamples": args.resamples, "bootstrap_seed": BOOTSTRAP_SEED,
                       "llm_calls": 0},
            "compliance_disagreements": disagreements,
            "summary": summary,
            "records": records,
            "note": "offline scoring of the frozen run; no new LLM calls; no tuning on eval cases",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n": keep LF on Windows too, plus a final newline.
        with args.out.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        print(f"Saved: {args.out}")

    if not official:
        return 1
    return 0 if total["f1"] is not None and total["f1"] >= TARGET_F1 else 1


if __name__ == "__main__":
    sys.exit(main())
