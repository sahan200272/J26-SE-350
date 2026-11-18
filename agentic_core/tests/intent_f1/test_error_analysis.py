"""Tests for scripts/intent_f1_error_analysis.py on hand-made plans only."""

from datetime import date

from agentic_core.tests.intent_f1.scorer import expected_plan, predicted_plan
from scripts.intent_f1_error_analysis import analyse_case

REF = date(2026, 1, 5)  # a Monday


def _plans(expected, raw):
    return expected_plan(expected, REF), *predicted_plan(raw, REF)


def test_causes_and_lenient_counts():
    expected = {"notes": [{"title": "Survey progress bar", "body": "b", "folder": "Ideas"}],
                "events": [{"title": "Survey discussion", "day": "tuesday", "time": "15:00",
                            "attendees": []}]}
    raw = ('{"notes": [{"title": "Idea", "body": "progress bar"},'
           ' {"title": "Meeting", "body": "Tuesday 3 pm"}],'
           ' "events": [{"title": "Meeting", "day": "tomorrow", "time": "15:00", "attendees": []}]}')
    E, P, ok = _plans(expected, raw)
    extras, misses, lenient = analyse_case("multi_intent", E, P, ok)
    assert extras == {"copy_of_event": 1, "note_title_differs": 1, "right_slot_title_differs": 1}
    assert misses == {"right_slot_title_differs": 1, "note_title_differs": 1}
    assert lenient == (2, 1, 0)


def test_noise_and_non_compliant():
    E, P, ok = _plans({"notes": [], "events": []}, '{"notes": [{"title": "Lunch", "body": "x"}], "events": []}')
    extras, misses, _ = analyse_case("noise", E, P, ok)
    assert extras == {"noise_case": 1} and not misses
    E, P, ok = _plans({"notes": [{"title": "Look at bugs", "body": "b", "folder": "Inbox"}], "events": []},
                      "not json")
    extras, misses, lenient = analyse_case("ambiguous", E, P, ok)
    assert misses == {"non_compliant": 1} and not extras
    assert lenient == (0, 0, 1)
