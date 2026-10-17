"""Read a diarized Markdown transcript (the format agreed with Component 1)."""

import re
from dataclasses import dataclass
from pathlib import Path


class TranscriptFormatError(ValueError):
    """The transcript does not follow the agreed format."""


@dataclass(frozen=True)
class Turn:
    """One speaker turn: when it started, who spoke, and what was said."""

    start_s: float
    speaker: str
    text: str
    line_no: int


@dataclass(frozen=True)
class Transcript:
    """A whole recording: header facts plus the list of turns."""

    recording_id: str | None
    started_at: str | None
    speakers: int | None
    turns: tuple[Turn, ...]


# Matches:  [HH:MM:SS] Speaker N: text
_TURN_PATTERN = re.compile(r"^\[(\d+):([0-5]\d):([0-5]\d)\]\s+([^:\]]+?):\s*(.*)$")


def _read_header(lines: list[str]) -> tuple[dict[str, str], int]:
    """reads the header section at the beginning of a transcript file and converts it into a Python dictionary"""
    first = 0
    while first < len(lines) and not lines[first].strip():
        first += 1
    if first >= len(lines) or lines[first].strip() != "---":
        return {}, 0  # no header; that is allowed

    header: dict[str, str] = {}
    for index in range(first + 1, len(lines)):
        line = lines[index].strip()
        if line == "---":
            return header, index + 1
        if not line:
            continue
        if ":" not in line:
            raise TranscriptFormatError(f"line {index + 1}: bad header line: {line!r}")
        key, value = line.split(":", 1)
        header[key.strip()] = value.strip()
    raise TranscriptFormatError("header started with --- but was never closed")


def parse_transcript(text: str) -> Transcript:
    """Turn transcript text into a Transcript. Raises TranscriptFormatError."""
    lines = text.splitlines()
    header, body_start = _read_header(lines)

    turns: list[Turn] = []
    for index in range(body_start, len(lines)):
        raw = lines[index].strip()
        line_no = index + 1
        if not raw:
            continue

        match = _TURN_PATTERN.match(raw)
        if match is None:
            raise TranscriptFormatError(f"line {line_no}: not a valid turn: {raw!r}")

        hours, minutes, seconds, speaker, body = match.groups()
        body = body.strip()
        if not body:
            raise TranscriptFormatError(f"line {line_no}: turn has empty text")

        start_s = float(int(hours) * 3600 + int(minutes) * 60 + int(seconds))
        if turns and start_s < turns[-1].start_s:
            raise TranscriptFormatError(f"line {line_no}: time goes backwards")

        turns.append(Turn(start_s, speaker.strip(), body, line_no))

    if not turns:
        raise TranscriptFormatError("no speaker turns found")

    speakers = None
    if "speakers" in header:
        try:
            speakers = int(header["speakers"])
        except ValueError:
            raise TranscriptFormatError("header 'speakers' must be a whole number") from None

    return Transcript(
        recording_id=header.get("recording_id"),
        started_at=header.get("started_at"),
        speakers=speakers,
        turns=tuple(turns),
    )


def parse_transcript_file(path: str | Path) -> Transcript:
    """Read a transcript file from disk and parse it."""
    # utf-8-sig also removes the hidden BOM mark that Windows editors may add.
    return parse_transcript(Path(path).read_text(encoding="utf-8-sig"))