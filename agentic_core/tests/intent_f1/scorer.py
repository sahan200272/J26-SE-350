"""Intent F1 scorer (RP-17). Helper module, not a test. Rules only, no LLM.

See docs/evaluation/intent_f1_definition.md (agreed before any scoring).
In short: the model's raw answer and the expected answer both go through the
same DraftPlan check and resolve_plan. Then notes are matched to notes and
events to events, one to one, and we count hits (TP), misses (FN) and
extras (FP).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from agentic_core.decoding.plan_schema import ActionPlan, DraftPlan
from agentic_core.decoding.resolver import resolve_plan

TARGET_F1 = 0.90
THRESHOLD = 0.5  # untuned guess, fixed in the definition before scoring
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 17
STOP_WORDS = frozenset(
    "a an the to of for and or with about on in at by from "
    "our my your we us i you this that it is be will".split()
)
SCORED_CATEGORIES = ("single_intent", "multi_intent", "ambiguous")
NOISE = "noise"

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


def title_words(title: str) -> frozenset[str]:
    """Lower-case words of a title, without stop words."""
    return frozenset(w for w in _WORD_SPLIT.split(title.lower()) if w and w not in STOP_WORDS)


def overlap(a: str, b: str) -> float:
    """Jaccard overlap of two titles' words. 0.0 if either has no words."""
    wa, wb = title_words(a), title_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def expected_plan(expected: dict, reference: date) -> ActionPlan:
    """The expected answer in final-plan form. Raises if it breaks the schema."""
    return resolve_plan(DraftPlan.model_validate(expected), reference)


def predicted_plan(raw_output: str | None, reference: date) -> tuple[ActionPlan, bool]:
    """The plan the system would act on, and whether the answer was compliant.

    A non-compliant answer (bad JSON or schema error) gives an EMPTY plan,
    because extract_plan returns no plan for it.
    """
    try:
        draft = DraftPlan.model_validate_json(raw_output or "")
    except ValidationError:
        return ActionPlan(notes=[], events=[]), False
    return resolve_plan(draft, reference), True


def pair_items(expected: list, predicted: list, can_match) -> list[tuple[int, int, float]]:
    """One-to-one greedy pairing.

    All matching pairs are sorted by overlap (highest first; ties by position in
    the expected list, then the predicted list) and taken while both items are free.
    """
    candidates = []
    for i, exp in enumerate(expected):
        for j, pred in enumerate(predicted):
            if can_match(exp, pred):
                candidates.append((-overlap(exp.title, pred.title), i, j))
    candidates.sort()
    used_e, used_p, pairs = set(), set(), []
    for neg, i, j in candidates:
        if i not in used_e and j not in used_p:
            used_e.add(i)
            used_p.add(j)
            pairs.append((i, j, -neg))
    return sorted(pairs, key=lambda p: p[0])


def _note_match(exp, pred) -> bool:
    return overlap(exp.title, pred.title) >= THRESHOLD


def _event_match(exp, pred) -> bool:
    return exp.start == pred.start and overlap(exp.title, pred.title) >= THRESHOLD


def _names(names: list[str]) -> set[str]:
    return {n.lower() for n in names}


@dataclass
class TypeScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0


@dataclass
class CaseScore:
    notes: TypeScore = field(default_factory=TypeScore)
    events: TypeScore = field(default_factory=TypeScore)
    misses: list[str] = field(default_factory=list)  # expected items with no pair
    extras: list[str] = field(default_factory=list)  # predicted items with no pair
    folder_checked: int = 0
    folder_correct: int = 0
    attendees_checked: int = 0
    attendees_correct: int = 0

    @property
    def tp(self) -> int:
        return self.notes.tp + self.events.tp

    @property
    def fp(self) -> int:
        return self.notes.fp + self.events.fp

    @property
    def fn(self) -> int:
        return self.notes.fn + self.events.fn


def score_case(expected: ActionPlan, predicted: ActionPlan) -> CaseScore:
    """Count hits, misses and extras for one case."""
    score = CaseScore()

    pairs = pair_items(expected.notes, predicted.notes, _note_match)
    score.notes = TypeScore(len(pairs), len(predicted.notes) - len(pairs),
                            len(expected.notes) - len(pairs))
    for i, j, _ in pairs:
        score.folder_checked += 1
        score.folder_correct += expected.notes[i].folder == predicted.notes[j].folder
    _record_unpaired(score, "note", expected.notes, predicted.notes, pairs, _describe_note)

    pairs = pair_items(expected.events, predicted.events, _event_match)
    score.events = TypeScore(len(pairs), len(predicted.events) - len(pairs),
                             len(expected.events) - len(pairs))
    for i, j, _ in pairs:
        score.attendees_checked += 1
        score.attendees_correct += (_names(expected.events[i].attendees)
                                    == _names(predicted.events[j].attendees))
    _record_unpaired(score, "event", expected.events, predicted.events, pairs, _describe_event)
    return score


def _describe_note(note) -> str:
    return f"note '{note.title}' ({note.folder})"


def _describe_event(event) -> str:
    return f"event '{event.title}' {event.start.isoformat(timespec='minutes')}"


def _record_unpaired(score, kind, expected, predicted, pairs, describe) -> None:
    paired_e = {i for i, _, _ in pairs}
    paired_p = {j for _, j, _ in pairs}
    score.misses += [describe(x) for i, x in enumerate(expected) if i not in paired_e]
    score.extras += [describe(x) for j, x in enumerate(predicted) if j not in paired_p]


def prf(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    """Precision, recall, F1. None where the value cannot be calculated."""
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if tp + fp + fn == 0:
        f1 = None
    else:
        f1 = 2 * tp / (2 * tp + fp + fn)  # same as 2PR/(P+R); 0.0 when tp is 0
    return {"precision": precision, "recall": recall, "f1": f1}


def _totals(cases: list[dict]) -> dict[str, Any]:
    tp = sum(c["score"].tp for c in cases)
    fp = sum(c["score"].fp for c in cases)
    fn = sum(c["score"].fn for c in cases)
    return {"cases": len(cases), "tp": tp, "fp": fp, "fn": fn, **prf(tp, fp, fn),
            "exact_cases": sum(1 for c in cases if c["score"].fp == 0 and c["score"].fn == 0)}


def micro_f1(cases: list[dict]) -> float | None:
    return _totals(cases)["f1"]


def bootstrap_interval(cases: list[dict], resamples: int = BOOTSTRAP_RESAMPLES,
                       seed: int = BOOTSTRAP_SEED) -> tuple[float, float] | None:
    """95% percentile bootstrap interval for micro F1, resampling whole cases."""
    if not cases:
        return None
    counts = [(c["score"].tp, c["score"].fp, c["score"].fn) for c in cases]
    rng = random.Random(seed)
    n = len(counts)
    values = []
    for _ in range(resamples):
        tp = fp = fn = 0
        for _ in range(n):
            a, b, d = counts[rng.randrange(n)]
            tp, fp, fn = tp + a, fp + b, fn + d
        if tp + fp + fn:
            values.append(2 * tp / (2 * tp + fp + fn))
    if not values:
        return None
    values.sort()
    low = values[int(0.025 * (len(values) - 1))]
    high = values[int(0.975 * (len(values) - 1))]
    return low, high


def summarize(cases: list[dict], resamples: int = BOOTSTRAP_RESAMPLES) -> dict[str, Any]:
    """All numbers from the definition.

    Each item of `cases` is {"id", "category", "compliant", "score": CaseScore}.
    """
    total = _totals(cases)
    interval = bootstrap_interval(cases, resamples)
    total["ci95_low"], total["ci95_high"] = interval if interval else (None, None)

    notes = [{"score": CaseScore(notes=c["score"].notes)} for c in cases]
    events = [{"score": CaseScore(events=c["score"].events)} for c in cases]

    by_category: dict[str, Any] = {}
    for cat in SCORED_CATEGORIES:
        subset = [c for c in cases if c["category"] == cat]
        if subset:
            by_category[cat] = _totals(subset)
    noise = [c for c in cases if c["category"] == NOISE]
    if noise:
        by_category[NOISE] = {
            "cases": len(noise),
            "fp": sum(c["score"].fp for c in noise),
            "clean_cases": sum(1 for c in noise if c["score"].fp == 0),
            "clean_case_rate": sum(1 for c in noise if c["score"].fp == 0) / len(noise),
        }

    failed = [c for c in cases if not c["compliant"]]
    fc = sum(c["score"].folder_checked for c in cases)
    ac = sum(c["score"].attendees_checked for c in cases)
    f1 = total["f1"]
    return {
        "total": total,
        "result": None if f1 is None else ("MET" if f1 >= TARGET_F1 else "NOT MET"),
        "notes_only": {k: v for k, v in _totals(notes).items() if k != "exact_cases"},
        "events_only": {k: v for k, v in _totals(events).items() if k != "exact_cases"},
        "by_category": by_category,
        "exact_case_rate": total["exact_cases"] / len(cases) if cases else None,
        "non_compliant": {"cases": len(failed), "fn_from_them": sum(c["score"].fn for c in failed)},
        "folder_accuracy": {"checked": fc,
                            "correct": sum(c["score"].folder_correct for c in cases),
                            "rate": sum(c["score"].folder_correct for c in cases) / fc if fc else None},
        "attendees_accuracy": {"checked": ac,
                               "correct": sum(c["score"].attendees_correct for c in cases),
                               "rate": sum(c["score"].attendees_correct for c in cases) / ac if ac else None},
    }


def check_run(run: dict, cases: list[dict], frozen_fingerprint: str, dataset_fingerprint: str) -> list[str]:
    """Reasons the frozen run cannot be scored. Empty list = OK."""
    problems = []
    if run.get("official") is not True:
        problems.append("run is not official")
    if run.get("all_run") is not True or run.get("cases_run") != len(cases):
        problems.append("not all cases ran")
    if run.get("summary", {}).get("total", {}).get("infra_errors", 1) != 0:
        problems.append("run has infra errors")
    if dataset_fingerprint != frozen_fingerprint:
        problems.append("eval_cases.json does not match the frozen fingerprint")
    if run.get("dataset_fingerprint") != frozen_fingerprint:
        problems.append("run was made on a different dataset")
    record_ids = [r.get("id") for r in run.get("records", [])]
    if sorted(record_ids) != sorted(c["id"] for c in cases) or len(set(record_ids)) != len(record_ids):
        problems.append("run record ids do not equal the case ids")
    if any(r.get("status") != "ran" for r in run.get("records", [])):
        problems.append("some records did not run")
    return problems
