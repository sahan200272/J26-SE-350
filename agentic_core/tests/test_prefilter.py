"""Tests for the rules-first prefilter (RP-14, section 3). No LLM is used here."""
from pathlib import Path

import pytest

from agentic_core.decoding.prefilter import check_segment, find_action_cues
from agentic_core.segmentation.segmenter import Segment, segment_transcript
from agentic_core.segmentation.transcript import Turn, parse_transcript_file

SAMPLE = Path(__file__).resolve().parents[1] / "datasets" / "segmentation" / "sample_standup.md"


def make_segment(*texts: str, start_s: float = 630.0) -> Segment:
    """Build a one-segment example. The default start (630 s) prints as 00:10:30."""
    turns = tuple(
        Turn(start_s=start_s + i, speaker="Speaker 1", text=text, line_no=i + 1)
        for i, text in enumerate(texts)
    )
    return Segment(
        index=0, turns=turns, started_because="start", est_tokens=10, oversized=False
    )


def test_sample_standup_gate_decisions():
    segments = segment_transcript(parse_transcript_file(SAMPLE))
    decisions = [check_segment(segment).needs_llm for segment in segments]
    # Topic 1 (review) and topic 2 (demo) have tasks. Topic 3 is only lunch chat.
    assert decisions == [True, True, False]


@pytest.mark.parametrize("text", [
    "I'll send the report tomorrow.",
    "Let's meet on Friday at 3 pm.",
    "Please remind Kasun about the laptop.",
    "The deadline is 30 October.",
    "We need to fix the cache.",
    "Write this down: use Redis for sessions.",
    "What if we cache the results?",
    "Call me at 10:30.",
    "I am booking the room.",
])
def test_task_like_sentences_go_to_the_llm(text):
    assert check_segment(make_segment(text)).needs_llm is True


@pytest.mark.parametrize("text", [
    "Morning, how was your weekend?",
    "It was great, we went to the beach.",
    "Sounds good.",
    "The weather is nice.",
    "I like mustard.",      # "must" inside another word must not count
])
def test_small_talk_is_skipped(text):
    result = check_segment(make_segment(text))
    assert result.needs_llm is False
    assert result.cues == ()


def test_timestamps_and_speaker_labels_are_not_cues():
    # The time stamp 00:10:30 looks like a clock time. It must be ignored.
    segment = make_segment("Nice weather.")
    assert "00:10:30" in segment.to_text()
    assert check_segment(segment).needs_llm is False


def test_curly_apostrophe_is_understood():
    assert find_action_cues("I\u2019ll do it.") == ("i'll",)


def test_cues_are_listed_in_order_without_duplicates():
    cues = find_action_cues("Please send it. Please send it tomorrow.")
    assert cues == ("please", "send", "tomorrow")


def test_empty_text_has_no_cues():
    assert find_action_cues("") == ()