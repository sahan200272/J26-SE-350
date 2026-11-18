"""Error analysis for the official intent F1 score (RP-17). NOT the result.

Sorts every miss (FN) and extra (FP) of the frozen run into a cause, and
works out a lenient upper bound. Rules only, no LLM. It does not change the
official score in docs/evaluation/intent_f1_official.json.

Run from the repo root:
    python -m scripts.intent_f1_error_analysis --out docs/evaluation/intent_f1_error_analysis.json

Causes (the first rule that fits wins):
  extras: noise_case, copy_of_event (a note that repeats a predicted event),
          right_slot_title_differs (event), note_title_differs, other
  misses: non_compliant, right_slot_title_differs (event), type_swap,
          note_title_differs, not_found
Lenient bound: notes paired by count only (titles ignored), events paired by
date and time only. It shows how much of the gap the matching rule explains.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from agentic_core.decoding.plan_schema import ActionPlan
from agentic_core.segmentation.transcript import parse_transcript
from agentic_core.tests.intent_f1.scorer import (
    NOISE,
    THRESHOLD,
    expected_plan,
    overlap,
    pair_items,
    predicted_plan,
    prf,
)
from agentic_core.tests.schema_compliance.cases import EVAL_PATH, load_cases, recording_date

OFFICIAL_RUN = Path("docs/evaluation/schema_compliance_official.json")


def _close(a, b) -> bool:
    return overlap(a.title, b.title) >= THRESHOLD


def analyse_case(category: str, expected: ActionPlan, predicted: ActionPlan,
                 compliant: bool) -> tuple[Counter, Counter, tuple[int, int, int]]:
    """Causes of extras and misses for one case, and its lenient (tp, fp, fn)."""
    extras, misses = Counter(), Counter()
    E, P = expected, predicted

    n_pairs = pair_items(E.notes, P.notes, _close)
    e_pairs = pair_items(E.events, P.events, lambda a, b: a.start == b.start and _close(a, b))
    free_en = [x for i, x in enumerate(E.notes) if i not in {p[0] for p in n_pairs}]
    free_pn = [x for j, x in enumerate(P.notes) if j not in {p[1] for p in n_pairs}]
    free_ee = [x for i, x in enumerate(E.events) if i not in {p[0] for p in e_pairs}]
    free_pe = [x for j, x in enumerate(P.events) if j not in {p[1] for p in e_pairs}]

    for note in free_pn:
        if category == NOISE:
            extras["noise_case"] += 1
        elif any(_close(note, ev) for ev in P.events):
            extras["copy_of_event"] += 1
        elif free_en:
            extras["note_title_differs"] += 1
        else:
            extras["other"] += 1
    for ev in free_pe:
        if category == NOISE:
            extras["noise_case"] += 1
        elif any(ev.start == x.start for x in free_ee):
            extras["right_slot_title_differs"] += 1
        else:
            extras["other"] += 1

    for ev in free_ee:
        if not compliant:
            misses["non_compliant"] += 1
        elif any(ev.start == x.start for x in free_pe):
            misses["right_slot_title_differs"] += 1
        elif any(_close(ev, n) for n in free_pn):
            misses["type_swap"] += 1
        else:
            misses["not_found"] += 1
    for note in free_en:
        if not compliant:
            misses["non_compliant"] += 1
        elif any(_close(note, ev) for ev in free_pe):
            misses["type_swap"] += 1
        elif free_pn:
            misses["note_title_differs"] += 1
        else:
            misses["not_found"] += 1

    lenient_notes = min(len(E.notes), len(P.notes))
    lenient_events = len(pair_items(E.events, P.events, lambda a, b: a.start == b.start))
    tp = lenient_notes + lenient_events
    lenient = (tp, len(P.notes) + len(P.events) - tp, len(E.notes) + len(E.events) - tp)
    return extras, misses, lenient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Intent F1 error analysis (RP-17), not the result")
    parser.add_argument("--run", type=Path, default=OFFICIAL_RUN)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    run = {r["id"]: r for r in json.loads(args.run.read_text(encoding="utf-8"))["records"]}
    extras, misses = Counter(), Counter()
    tp = fp = fn = 0
    for case in load_cases(EVAL_PATH):
        reference = recording_date(parse_transcript(case["transcript"]).started_at)
        predicted, compliant = predicted_plan(run[case["id"]].get("raw_output"), reference)
        e, m, (a, b, c) = analyse_case(case["category"], expected_plan(case["expected"], reference),
                                       predicted, compliant)
        extras += e
        misses += m
        tp, fp, fn = tp + a, fp + b, fn + c

    lenient = {"tp": tp, "fp": fp, "fn": fn, **prf(tp, fp, fn)}
    print("ERROR ANALYSIS (not the result)")
    print(f"extras (FP) {sum(extras.values())}: {dict(extras.most_common())}")
    print(f"misses (FN) {sum(misses.values())}: {dict(misses.most_common())}")
    print(f"lenient upper bound: F1 {100 * lenient['f1']:.1f}% "
          f"(precision {100 * lenient['precision']:.1f}%, recall {100 * lenient['recall']:.1f}%)")

    if args.out is not None:
        payload = {"note": "error analysis of the official run; NOT the result",
                   "run": args.run.as_posix(), "extras": dict(extras.most_common()),
                   "misses": dict(misses.most_common()), "lenient_upper_bound": lenient}
        with args.out.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
        print(f"Saved: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
