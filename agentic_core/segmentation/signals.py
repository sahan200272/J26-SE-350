"""Simple hints that a new topic starts at a speaker turn (no LLM needed)."""

import re
from dataclasses import dataclass

from agentic_core.segmentation.transcript import Transcript, Turn

# Assumption, not measured: people speak about 150 words per minute.
WORDS_PER_SECOND = 2.5

_CUE_PATTERN = re.compile(
    r"^(?:(?:okay|ok|right|so|alright|good)[,.]?\s+)?"
    r"(?:"
    r"next(?:[,.:!]|\s+(?:topic|item|up|point)\b|$)"
    r"|moving\s+on\b"
    r"|let['’]?s\s+(?:move\s+on|talk\s+about)\b"
    r"|on\s+another\s+note\b"
    r"|by\s+the\s+way\b"
    r"|anyway\b"
    r"|another\s+thing\b"
    r"|switching\s+to\b"
    r"|back\s+to\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TurnSignals:
    """Hints about one turn."""

    index: int
    gap_s: float | None  # time since the previous turn started
    pause_s: float | None  # estimated silence before this turn
    has_cue: bool  # turn opens with a topic-change phrase


def estimate_speech_s(text: str) -> float:
    """Guess how many seconds it took to say this text."""
    return len(text.split()) / WORDS_PER_SECOND


def has_topic_cue(text: str) -> bool:
    """True if the text opens with a topic-change phrase."""
    return _CUE_PATTERN.match(text.strip()) is not None


def compute_signals(transcript: Transcript) -> list[TurnSignals]:
    """Work out the hints for every turn, in order."""
    signals: list[TurnSignals] = []
    previous: Turn | None = None
    for index, turn in enumerate(transcript.turns):
        if previous is None:
            gap = None
            pause = None
        else:
            gap = turn.start_s - previous.start_s
            pause = max(0.0, gap - estimate_speech_s(previous.text))
        signals.append(TurnSignals(index, gap, pause, has_topic_cue(turn.text)))
        previous = turn
    return signals