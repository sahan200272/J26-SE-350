"""Rules-first gate: decide if a segment is worth an LLM call (RP-14, section 3).

Trade-off (speed vs recall): the cue lists below are deliberately BROAD, so a
segment is skipped only when it shows no sign of a task, a time, or an idea
worth noting. This protects recall (and the F1 target) but means more slow
LLM calls.

All cue lists are untuned guesses. Do NOT tune them on the 200 evaluation
scenarios. Tune on a separate development set instead.
"""

import re
from dataclasses import dataclass

from agentic_core.segmentation.segmenter import Segment

# Phrases that sound like a promise, a request, or a job to do.
_COMMITMENT_CUES = (
    r"i\s+will", r"i'll", r"we\s+will", r"we'll",
    r"i\s+am\s+going\s+to", r"i'm\s+going\s+to",
    r"we\s+are\s+going\s+to", r"we're\s+going\s+to",
    r"let's", r"let\s+us",
    r"please", r"don't\s+forget", r"make\s+sure",
    r"need\s+to", r"needs\s+to", r"have\s+to", r"has\s+to", r"must",
    r"can\s+you", r"could\s+you", r"would\s+you",
    r"follow[\s-]?up", r"action\s+items?", r"to-?do", r"deadline", r"due",
    r"remind(?:s|ed|ing|er)?",
    r"book(?:s|ed|ing)?", r"schedul(?:e|es|ed|ing)", r"arrang(?:e|es|ed|ing)",
    r"reserv(?:e|es|ed|ing)", r"send(?:s|ing)?", r"email(?:s|ed|ing)?",
)

# Meetings, days, months and clock times. Bare "today" is left out on purpose
# because it shows up in small talk ("nice weather today").
_WEEKDAYS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_MONTHS = (
    r"(?:january|february|march|april|june|july|august|september|"
    r"october|november|december)"  # "may" left out: too common as a normal word
)
_TIME_CUES = (
    r"meet(?:s|ing|ings)?", r"appointments?", r"calendar",
    _WEEKDAYS, _MONTHS, r"tomorrow", r"tonight",
    r"next\s+(?:week|month)", r"this\s+(?:week|weekend)",
    r"end\s+of\s+(?:the\s+)?(?:day|week|month)",
    r"o'clock",
    r"\d{1,2}(?::\d{2})?\s?(?:am|pm)",
    r"(?<![\d:])\d{1,2}:\d{2}(?![\d:])",
)

# Ideas and things people ask to be remembered.
_NOTE_CUES = (
    r"ideas?", r"remember", r"write\s+(?:this\s+)?down",
    r"note\s+(?:that|this|down)", r"keep\s+in\s+mind", r"what\s+if",
    r"we\s+could", r"proposals?", r"suggest(?:s|ed|ion|ions)?",
)

_CUE_PATTERN = re.compile(
    r"\b(?:" + "|".join(_COMMITMENT_CUES + _TIME_CUES + _NOTE_CUES) + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PrefilterResult:
    """The gate's answer for one segment."""

    needs_llm: bool
    cues: tuple[str, ...]  # which cues were found (empty means skip)


def _normalise(text: str) -> str:
    """Turn curly apostrophes into plain ones so "I\u2019ll" matches "i'll"."""
    return text.replace("\u2019", "'").replace("\u2018", "'")


def find_action_cues(text: str) -> tuple[str, ...]:
    """List the distinct cues found in the text, in the order they appear."""
    found: list[str] = []
    for match in _CUE_PATTERN.finditer(_normalise(text)):
        cue = " ".join(match.group(0).lower().split())
        if cue not in found:
            found.append(cue)
    return tuple(found)


def check_segment(segment: Segment) -> PrefilterResult:
    """Decide whether this segment should be sent to the LLM.

    Only the spoken words are searched. Time stamps like [00:10:30] and
    speaker labels like "Speaker 1" are left out on purpose, so they can
    never look like a clock time or a cue.
    """
    spoken_text = "\n".join(turn.text for turn in segment.turns)
    cues = find_action_cues(spoken_text)
    return PrefilterResult(needs_llm=bool(cues), cues=cues)