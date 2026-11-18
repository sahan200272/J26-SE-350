"""Unit tests for the intent F1 scorer (RP-17).

All examples are small and hand-made. None of them comes from the 200 eval
cases, so the scorer is never tuned on the evaluation data.
"""

import json
from datetime import date

import pytest

from agentic_core.tests.intent_f1.scorer import (
    STOP_WORDS,
    THRESHOLD,
    bootstrap_interval,
    check_run,
    expected_plan,
    overlap,
    predicted_plan,
    prf,
    score_case,
    summarize,
    title_words,
)

REF = date(2026, 1, 5)  # a Monday


def plan(notes=(), events=()):
    return {"notes": list(notes), "events": list(events)}


def note(title, body="body", folder="Inbox"):
    return {"title": title, "body": body, "folder": folder}


def event(title, day="tuesday", time="10:00", attendees=()):
    return {"title": title, "day": day, "time": time, "attendees": list(attendees)}


def score(expected: dict, predicted: dict | str):
    raw = predicted if isinstance(predicted, str) else json.dumps(predicted)
    pred, compliant = predicted_plan(raw, REF)
    return score_case(expected_plan(expected, REF), pred), compliant


# --- title words and overlap ---------------------------------------------

def test_threshold_and_stop_words_are_the_agreed_ones():
    assert THRESHOLD == 0.5
    assert {"the", "a", "with", "about", "will"} <= STOP_WORDS
    assert len(STOP_WORDS) == 28


def test_title_words_lowercases_splits_and_drops_stop_words():
    assert title_words("Review THE budget-plan, v2!") == {"review", "budget", "plan", "v2"}


def test_overlap_is_jaccard():
    assert overlap("Budget review", "budget review") == 1.0
    assert overlap("Budget review", "Review of the budget") == 1.0
    assert overlap("Clean staging database", "Staging database cleanup") == 0.5
    assert overlap("Budget review", "Lunch plans") == 0.0


def test_overlap_is_zero_when_a_title_has_only_stop_words():
    assert overlap("The", "the") == 0.0


# --- predicted plan -------------------------------------------------------

def test_bad_json_gives_empty_plan_and_all_expected_are_misses():
    s, compliant = score(plan([note("Buy paper")], [event("Budget review")]), '{"notes": [')
    assert not compliant
    assert (s.tp, s.fp, s.fn) == (0, 0, 2)


def test_schema_error_gives_empty_plan():
    bad = plan(events=[event("Budget review", time="")])  # empty time breaks DraftEvent
    s, compliant = score(plan(events=[event("Budget review")]), bad)
    assert not compliant
    assert (s.tp, s.fp, s.fn) == (0, 0, 1)


def test_expected_plan_that_breaks_schema_raises():
    with pytest.raises(Exception):
        expected_plan(plan(events=[event("X", time="10am")]), REF)


# --- note matching --------------------------------------------------------

def test_note_matches_on_title_overlap_only():
    s, _ = score(plan([note("Clean staging database", body="a")]),
                 plan([note("Staging database cleanup", body="totally different")]))
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_note_below_threshold_is_one_miss_and_one_extra():
    s, _ = score(plan([note("Clean staging database server")]),  # 4 words
                 plan([note("Staging database cleanup")]))  # overlap 2/5 = 0.4
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)
    assert s.misses == ["note 'Clean staging database server' (Inbox)"]
    assert s.extras == ["note 'Staging database cleanup' (Inbox)"]


def test_wrong_folder_still_matches_but_is_counted_in_folder_accuracy():
    s, _ = score(plan([note("Progress bar idea", folder="Ideas")]),
                 plan([note("Progress bar idea")]))  # folder missing -> Inbox
    assert s.tp == 1
    assert (s.folder_checked, s.folder_correct) == (1, 0)


# --- event matching -------------------------------------------------------

def test_event_needs_same_day_and_time():
    s, _ = score(plan(events=[event("Budget review", time="10:00")]),
                 plan(events=[event("Budget review", time="11:00")]))
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)
    s, _ = score(plan(events=[event("Budget review", day="tuesday")]),
                 plan(events=[event("Budget review", day="wednesday")]))
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_event_day_words_are_compared_as_real_dates():
    # Recording day is Monday 5 Jan, so "tomorrow" and "tuesday" are the same date.
    s, _ = score(plan(events=[event("Budget review", day="tuesday")]),
                 plan(events=[event("Budget review", day="tomorrow")]))
    assert s.tp == 1


def test_event_needs_title_overlap():
    s, _ = score(plan(events=[event("Budget review")]), plan(events=[event("Team lunch")]))
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_attendees_not_in_match_and_speaker_labels_are_dropped():
    s, _ = score(plan(events=[event("Budget review")]),
                 plan(events=[event("Budget review", attendees=["Speaker 1", "", "speaker 2"])]))
    assert s.tp == 1
    assert (s.attendees_checked, s.attendees_correct) == (1, 1)
    s, _ = score(plan(events=[event("Budget review", attendees=["Chamari"])]),
                 plan(events=[event("Budget review", attendees=["chamari", "Nimal"])]))
    assert s.tp == 1
    assert s.attendees_correct == 0


# --- type swaps, duplicates, pairing --------------------------------------

def test_note_answered_as_event_is_a_miss_and_an_extra():
    s, _ = score(plan([note("Catch up with sales team")]),
                 plan(events=[event("Catch up with sales team")]))
    assert (s.notes.fn, s.events.fp, s.tp) == (1, 1, 0)


def test_exact_duplicate_prediction_is_removed_by_resolver():
    s, _ = score(plan([note("Buy paper", body="b")]),
                 plan([note("Buy paper", body="b"), note("buy  paper", body="B")]))
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_near_duplicate_prediction_is_an_extra():
    s, _ = score(plan([note("Buy paper", body="b")]),
                 plan([note("Buy paper", body="b"), note("Buy paper", body="other body")]))
    assert (s.tp, s.fp, s.fn) == (1, 1, 0)


def test_pairing_is_one_to_one_and_prefers_highest_overlap():
    expected = plan([note("Budget plan draft"), note("Budget plan")])
    predicted = plan([note("Budget plan")])
    s, _ = score(expected, predicted)
    assert (s.tp, s.fp, s.fn) == (1, 0, 1)
    assert s.misses == ["note 'Budget plan draft' (Inbox)"]


def test_noise_case_empty_answer_is_clean():
    s, _ = score(plan(), plan())
    assert (s.tp, s.fp, s.fn) == (0, 0, 0)


# --- totals ---------------------------------------------------------------

def test_prf_values_and_undefined_cases():
    assert prf(9, 1, 1)["f1"] == pytest.approx(0.9)
    assert prf(0, 2, 3) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    assert prf(0, 0, 0) == {"precision": None, "recall": None, "f1": None}
    assert prf(0, 0, 2)["precision"] is None


def _case(cid, category, expected, predicted):
    s, compliant = score(expected, predicted)
    return {"id": cid, "category": category, "compliant": compliant, "score": s}


def test_summarize_pools_noise_extras_into_main_f1():
    cases = [
        _case("A", "single_intent", plan([note("Buy paper")]), plan([note("Buy paper")])),
        _case("B", "noise", plan(), plan([note("Lunch was spicy")])),
        _case("C", "noise", plan(), plan()),
        _case("D", "ambiguous", plan([note("Look at bugs")]), "not json"),
    ]
    out = summarize(cases, resamples=200)
    assert (out["total"]["tp"], out["total"]["fp"], out["total"]["fn"]) == (1, 1, 1)
    assert out["total"]["f1"] == pytest.approx(0.5)
    assert out["result"] == "NOT MET"
    assert out["by_category"]["noise"] == {"cases": 2, "fp": 1, "clean_cases": 1,
                                          "clean_case_rate": 0.5}
    assert "f1" not in out["by_category"]["noise"]
    assert out["by_category"]["single_intent"]["f1"] == 1.0
    assert out["non_compliant"] == {"cases": 1, "fn_from_them": 1}
    assert out["exact_case_rate"] == 0.5
    assert out["notes_only"]["f1"] == pytest.approx(0.5)
    assert out["events_only"]["f1"] is None


def test_summarize_met_at_exactly_target():
    cases = [_case(str(i), "single_intent", plan([note("Buy paper")]), plan([note("Buy paper")]))
             for i in range(9)]
    cases.append(_case("x", "single_intent", plan([note("Buy paper")]), plan([note("Team lunch")])))
    out = summarize(cases, resamples=50)
    assert out["total"]["f1"] == pytest.approx(0.9)
    assert out["result"] == "MET"


def test_bootstrap_is_repeatable_and_inside_range():
    cases = [_case("A", "single_intent", plan([note("Buy paper")]), plan([note("Buy paper")])),
             _case("B", "single_intent", plan([note("Buy paper")]), plan([note("Team lunch")]))]
    first = bootstrap_interval(cases, resamples=500)
    assert first == bootstrap_interval(cases, resamples=500)
    assert 0.0 <= first[0] <= first[1] <= 1.0


# --- run validity ---------------------------------------------------------

def _run(**changes):
    run = {"official": True, "all_run": True, "cases_run": 2,
           "summary": {"total": {"infra_errors": 0}}, "dataset_fingerprint": "abc",
           "records": [{"id": "A", "status": "ran"}, {"id": "B", "status": "ran"}]}
    run.update(changes)
    return run


CASES = [{"id": "A"}, {"id": "B"}]


def test_check_run_accepts_a_good_run():
    assert check_run(_run(), CASES, "abc", "abc") == []


@pytest.mark.parametrize("changes, dataset_fp, reason", [
    ({"official": False}, "abc", "run is not official"),
    ({"cases_run": 1}, "abc", "not all cases ran"),
    ({"summary": {"total": {"infra_errors": 1}}}, "abc", "run has infra errors"),
    ({}, "zzz", "eval_cases.json does not match the frozen fingerprint"),
    ({"dataset_fingerprint": "zzz"}, "abc", "run was made on a different dataset"),
    ({"records": [{"id": "A", "status": "ran"}, {"id": "A", "status": "ran"}]}, "abc",
     "run record ids do not equal the case ids"),
    ({"records": [{"id": "A", "status": "ran"}, {"id": "B", "status": "infra_error"}]}, "abc",
     "some records did not run"),
])
def test_check_run_rejects_bad_runs(changes, dataset_fp, reason):
    assert reason in check_run(_run(**changes), CASES, "abc", dataset_fp)
