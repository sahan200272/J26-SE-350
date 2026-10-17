"""Turn one conversation segment into a validated action plan (RP-14, section 5).

Flow: prefilter (no LLM) -> one constrained LLM call -> strict check of the
draft -> code resolves dates and cleans up (no LLM).
There is no retry on purpose: the first-try result is the honest compliance
number. A failed answer is reported, never repaired silently.
"""

from dataclasses import dataclass
from datetime import date

from pydantic import ValidationError

from agentic_core.decoding.plan_schema import ActionPlan, DraftPlan
from agentic_core.decoding.prefilter import check_segment
from agentic_core.decoding.resolver import resolve_plan
from agentic_core.llm.client import LLMClient
from agentic_core.segmentation.segmenter import Segment

# Untuned guess. A short prompt on purpose: on CPU every prompt token costs time.
SYSTEM_PROMPT = (
    "You read part of a meeting transcript and list what the speakers clearly "
    "agreed to do. Reply with JSON only, with two lists.\n"
    "notes: ideas, decisions or reminders to save. Each needs a title and a body. "
    "folder is Inbox, Meetings or Ideas.\n"
    "events: meetings or deadlines. Add an event only if BOTH a day and a time "
    "were said. day is one of: today, tomorrow, monday, tuesday, wednesday, "
    "thursday, friday, saturday, sunday. time is 24-hour HH:MM, like 15:00. "
    "attendees are real names only.\n"
    "If a day or a time was not said, use a note instead. "
    "Never invent a day, a time or a name. Do not repeat an item.\n"
    'If nobody agreed to do anything, reply {"notes": [], "events": []}.'
)


@dataclass(frozen=True)
class ExtractionResult:
    """What happened for one segment."""

    plan: ActionPlan | None  # None means the model's answer was invalid
    skipped: bool  # True when the prefilter kept the LLM out of it
    error: str | None  # short reason when plan is None (never contains the transcript)
    tokens_out: int
    tpot_ms: float
    total_s: float


def build_user_prompt(segment: Segment) -> str:
    """The transcript text for the LLM.

    Time stamps are left out (they cost tokens and could be mistaken for
    meeting times). The recording date is left out too: the model only says
    "friday", and our code works out the real date.
    """
    return "Transcript:\n" + "\n".join(f"{turn.speaker}: {turn.text}" for turn in segment.turns)


def extract_plan(
    segment: Segment,
    client: LLMClient,
    reference_date: date,
    use_prefilter: bool = True,
) -> ExtractionResult:
    """Get a validated plan for one segment.

    Set use_prefilter=False to force the LLM call. The schema-compliance test
    needs that, because it measures the model, not the gate.
    reference_date is the day of the recording. It is used by our code only.
    """
    if use_prefilter and not check_segment(segment).needs_llm:
        return ExtractionResult(ActionPlan(notes=[], events=[]), True, None, 0, 0.0, 0.0)

    result = client.chat(
        build_user_prompt(segment),
        system_prompt=SYSTEM_PROMPT,
        response_format=DraftPlan.model_json_schema(),
    )

    try:
        draft, error = DraftPlan.model_validate_json(result.text), None
    except ValidationError as exc:
        first = exc.errors()[0]
        draft, error = None, f"{first['type']}: {first['msg']}"
        if result.tokens_out >= client.config.num_predict:
            error += " (output was cut off at the num_predict limit)"

    plan = resolve_plan(draft, reference_date) if draft else None
    return ExtractionResult(plan, False, error, result.tokens_out, result.tpot_ms, result.total_s)