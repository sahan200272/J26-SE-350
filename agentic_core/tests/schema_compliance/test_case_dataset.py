"""Structure checks for the schema-compliance case files (NFR-04).

These tests only look at the DATA. They never call the LLM.
"""

from collections import Counter

import pytest

from agentic_core.decoding.plan_schema import DraftPlan
from agentic_core.segmentation.segmenter import segment_transcript
from agentic_core.segmentation.transcript import parse_transcript
from agentic_core.tests.schema_compliance.cases import (
    CATEGORY_COUNTS,
    DEV_PATH,
    fingerprint,
    load_cases,
    recording_date,
)

# Frozen before the first run. If a case changes, this value must change on
# purpose, and the change will show in git history.
FROZEN_FINGERPRINT = "a03126ad762e34c735b0d0b4eacf3aa5e5282eafc9c6683ca37aef0713a8551d"

EVAL = load_cases()
DEV = load_cases(DEV_PATH)


def _spoken(case: dict) -> str:
    """The transcript without its header, so two cases can be compared."""
    return case["transcript"].split("---", 2)[2].strip()


def test_there_are_exactly_200_eval_cases_with_ordered_ids():
    assert [c["id"] for c in EVAL] == [f"SC-{i:03d}" for i in range(1, 201)]


def test_eval_split_matches_the_proposal():
    assert Counter(c["category"] for c in EVAL) == CATEGORY_COUNTS


def test_dev_set_has_20_cases_with_ordered_ids():
    assert [c["id"] for c in DEV] == [f"DEV-{i:02d}" for i in range(1, 21)]
    assert set(c["category"] for c in DEV) == set(CATEGORY_COUNTS)


@pytest.mark.parametrize("case", EVAL + DEV, ids=lambda c: c["id"])
def test_every_case_is_well_formed(case):
    assert set(case) == {"id", "category", "transcript", "expected"}
    assert case["category"] in CATEGORY_COUNTS

    transcript = parse_transcript(case["transcript"])
    assert transcript.started_at is not None
    recording_date(transcript.started_at)  # must be a real ISO date-time

    # One case = one segment, so the count of 200 stays exact.
    assert len(segment_transcript(transcript)) == 1

    # The expected plan must itself follow the schema the model is held to.
    expected = DraftPlan.model_validate(case["expected"])
    if case["category"] == "noise":
        assert expected.notes == [] and expected.events == []
    if case["category"] == "ambiguous":
        assert expected.events == [] and len(expected.notes) >= 1
    if case["category"] in ("single_intent", "multi_intent"):
        items = len(expected.notes) + len(expected.events)
        assert items == 1 if case["category"] == "single_intent" else items >= 2


def test_no_transcript_is_repeated_and_dev_is_separate_from_eval():
    eval_texts = [_spoken(c) for c in EVAL]
    dev_texts = [_spoken(c) for c in DEV]
    assert len(set(eval_texts)) == len(eval_texts)
    assert len(set(dev_texts)) == len(dev_texts)
    assert not set(eval_texts) & set(dev_texts)


def test_eval_cases_are_unchanged_since_they_were_frozen():
    assert fingerprint(EVAL) == FROZEN_FINGERPRINT
