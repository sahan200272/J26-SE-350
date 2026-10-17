from pathlib import Path

import pytest

from agentic_core.segmentation.signals import compute_signals, has_topic_cue
from agentic_core.segmentation.transcript import parse_transcript, parse_transcript_file

SAMPLE = Path(__file__).resolve().parents[2] / "datasets" / "segmentation" / "sample_standup.md"


def test_first_turn_has_no_gap():
    signals = compute_signals(parse_transcript_file(SAMPLE))
    assert signals[0].gap_s is None
    assert signals[0].pause_s is None


def test_pause_estimates_on_sample():
    signals = compute_signals(parse_transcript_file(SAMPLE))
    assert signals[3].gap_s == 87.0
    assert signals[3].pause_s == pytest.approx(83.8)
    assert signals[7].gap_s == 327.0
    assert signals[7].pause_s == pytest.approx(323.4)


def test_cues_found_only_where_expected_on_sample():
    signals = compute_signals(parse_transcript_file(SAMPLE))
    assert [s.index for s in signals if s.has_cue] == [3, 7]


def test_pause_is_never_negative():
    text = (
        "[00:00:00] Speaker 1: one two three four five six seven eight nine ten\n"
        "[00:00:01] Speaker 2: ok"
    )
    signals = compute_signals(parse_transcript(text))
    assert signals[1].gap_s == 1.0
    assert signals[1].pause_s == 0.0


@pytest.mark.parametrize(
    "text",
    [
        "Next, the demo on Friday.",
        "Okay. Next, the demo on Friday.",
        "By the way, where should we eat?",
        "Moving on to the budget.",
        "Let’s move on.",
        "Anyway, back to the bug.",
        "Next item: the budget.",
    ],
)
def test_cue_phrases_are_found(text):
    assert has_topic_cue(text)


@pytest.mark.parametrize(
    "text",
    [
        "I will do it next week.",
        "So next week we meet.",
        "Good. Please also remind Kasun.",
        "Next week is fine.",
        "The next item is hard.",
    ],
)
def test_normal_sentences_are_not_cues(text):
    assert not has_topic_cue(text)