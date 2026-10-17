from pathlib import Path

import pytest

from agentic_core.segmentation.transcript import (
    TranscriptFormatError,
    parse_transcript,
    parse_transcript_file,
)

SAMPLE = Path(__file__).resolve().parents[2] / "datasets" / "segmentation" / "sample_standup.md"


def test_sample_file_parses():
    transcript = parse_transcript_file(SAMPLE)
    assert transcript.recording_id == "2026-10-12_standup_01"
    assert transcript.speakers == 2
    assert len(transcript.turns) == 10
    assert transcript.turns[0].start_s == 4.0
    assert transcript.turns[0].speaker == "Speaker 1"
    assert transcript.turns[-1].start_s == 460.0


def test_colon_inside_text_is_kept():
    transcript = parse_transcript("[00:00:01] Speaker 1: Note: this has a colon")
    assert transcript.turns[0].text == "Note: this has a colon"


def test_header_is_optional():
    transcript = parse_transcript("[00:00:01] Speaker 1: Hello")
    assert transcript.recording_id is None
    assert len(transcript.turns) == 1


def test_hours_are_counted():
    transcript = parse_transcript("[01:02:03] Speaker 1: Hi")
    assert transcript.turns[0].start_s == 3723.0


def test_bad_line_reports_line_number():
    with pytest.raises(TranscriptFormatError, match="line 2"):
        parse_transcript("[00:00:01] Speaker 1: Hi\nthis is wrong")


def test_time_going_backwards_is_rejected():
    with pytest.raises(TranscriptFormatError, match="goes backwards"):
        parse_transcript("[00:00:10] Speaker 1: A\n[00:00:05] Speaker 2: B")


def test_empty_text_is_rejected():
    with pytest.raises(TranscriptFormatError, match="empty text"):
        parse_transcript("[00:00:01] Speaker 1:")


def test_empty_input_is_rejected():
    with pytest.raises(TranscriptFormatError, match="no speaker turns"):
        parse_transcript("")


def test_unclosed_header_is_rejected():
    with pytest.raises(TranscriptFormatError, match="never closed"):
        parse_transcript("---\nrecording_id: x\n[00:00:01] Speaker 1: Hi")


def test_file_with_bom_is_read(tmp_path):
    path = tmp_path / "bom.md"
    path.write_text("---\nrecording_id: abc\n---\n[00:00:01] Speaker 1: Hi\n", encoding="utf-8-sig")
    assert parse_transcript_file(path).recording_id == "abc"