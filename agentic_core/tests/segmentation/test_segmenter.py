from pathlib import Path

import pytest

from agentic_core.segmentation.segmenter import SegmentationConfig, segment_transcript
from agentic_core.segmentation.transcript import parse_transcript, parse_transcript_file

SAMPLE = Path(__file__).resolve().parents[2] / "datasets" / "segmentation" / "sample_standup.md"
TEN = "one two three four five six seven eight nine ten"


def test_sample_is_cut_into_three_topics():
    segments = segment_transcript(parse_transcript_file(SAMPLE))
    assert [len(s.turns) for s in segments] == [3, 4, 3]
    assert [s.started_because for s in segments] == ["start", "cue_and_pause", "long_pause"]
    assert [s.index for s in segments] == [0, 1, 2]
    assert not any(s.oversized for s in segments)


def test_every_turn_is_in_exactly_one_segment_in_order():
    transcript = parse_transcript_file(SAMPLE)
    segments = segment_transcript(transcript)
    joined = [turn for segment in segments for turn in segment.turns]
    assert joined == list(transcript.turns)


def test_quiet_normal_chat_stays_one_segment():
    text = f"[00:00:00] Speaker 1: {TEN}\n[00:00:05] Speaker 2: {TEN}"
    assert len(segment_transcript(parse_transcript(text))) == 1


def test_cue_with_small_pause_does_not_cut():
    text = "[00:00:00] Speaker 1: Hello there friend\n[00:00:03] Speaker 2: Anyway, I agree."
    assert len(segment_transcript(parse_transcript(text))) == 1


def test_long_pause_alone_cuts():
    text = "[00:00:00] Speaker 1: Hi\n[00:03:20] Speaker 2: Yes."
    segments = segment_transcript(parse_transcript(text))
    assert [s.started_because for s in segments] == ["start", "long_pause"]


def test_size_limit_cuts():
    text = (
        f"[00:00:00] Speaker 1: {TEN}\n"
        f"[00:00:05] Speaker 2: {TEN}\n"
        f"[00:00:10] Speaker 1: {TEN}"
    )
    segments = segment_transcript(parse_transcript(text), SegmentationConfig(max_segment_tokens=50))
    assert [len(s.turns) for s in segments] == [2, 1]
    assert [s.started_because for s in segments] == ["start", "size_limit"]


def test_single_huge_turn_is_flagged_oversized():
    text = "[00:00:00] Speaker 1: " + " ".join(["word"] * 30)
    segments = segment_transcript(parse_transcript(text), SegmentationConfig(max_segment_tokens=20))
    assert len(segments) == 1
    assert segments[0].oversized


def test_to_text_writes_transcript_lines():
    segments = segment_transcript(parse_transcript_file(SAMPLE))
    first_line = segments[1].to_text().splitlines()[0]
    assert first_line == "[00:01:42] Speaker 1: Okay. Next, the demo on Friday."


@pytest.mark.parametrize(
    "bad",
    [
        {"cue_pause_s": 200.0},  # bigger than long_pause_s
        {"max_segment_tokens": 0},
        {"long_pause_s": 0.0},
    ],
)
def test_bad_settings_are_rejected(bad):
    with pytest.raises(ValueError):
        SegmentationConfig(**bad)