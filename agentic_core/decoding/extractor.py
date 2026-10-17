"""Turn one conversation segment into a validated action plan (RP-14, section 4).

Flow: prefilter (no LLM) -> one constrained LLM call -> strict Pydantic check.
There is no retry on purpose: the first-try result is the honest compliance
number. A failed answer is reported, never repaired silently.
"""

from dataclasses import dataclass
from datetime import date

from pydantic import ValidationError

from agentic_core.decoding.plan_schema import ActionPlan
from agentic_core.decoding.prefilter import check_segment
from agentic_core.llm.client import LLMClient
from agentic_core.segmentation.segmenter import Segment

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Untuned guess. A short prompt on purpose: on CPU every prompt token costs time.
SYSTEM_PROMPT = (
    "You read part of a meeting transcript and list the actions the speakers "
    "clearly agreed to do. Reply with JSON only.\n"
    "Methods:\n"
    "- create_note: save an idea or decision. Needs a title and a body. "
    "folder is Inbox, Meetings or Ideas.\n"
    "- create_calendar_event: a meeting or deadline with a date and time. "
    "Needs a title and start as ISO 8601, like 2026-10-23T15:00:00. "
    "attendees is a list of names.\n"
    'If nobody agreed to do anything, reply {"actions": []}.\n'
    "Do not invent actions. Use the recording date to turn words like "
    "'Friday' into a real date."
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


def build_user_prompt(segment: Segment, reference_date: date) -> str:
    """The transcript text for the LLM. Time stamps are left out on purpose.

    They cost tokens and could be mistaken for meeting times. The plan does
    not need them.
    """
    lines = "\n".join(f"{turn.speaker}: {turn.text}" for turn in segment.turns)
    weekday = _WEEKDAYS[reference_date.weekday()]
    return f"Recording date: {reference_date.isoformat()} ({weekday})\n\nTranscript:\n{lines}"


def extract_plan(
    segment: Segment,
    client: LLMClient,
    reference_date: date,
    use_prefilter: bool = True,
) -> ExtractionResult:
    """Get a validated plan for one segment.

    Set use_prefilter=False to force the LLM call. The schema-compliance test
    needs that, because it measures the model, not the gate.
    """
    if use_prefilter and not check_segment(segment).needs_llm:
        return ExtractionResult(ActionPlan(actions=[]), True, None, 0, 0.0, 0.0)

    result = client.chat(
        build_user_prompt(segment, reference_date),
        system_prompt=SYSTEM_PROMPT,
        response_format=ActionPlan.model_json_schema(),
    )

    try:
        plan, error = ActionPlan.model_validate_json(result.text), None
    except ValidationError as exc:
        first = exc.errors()[0]
        plan, error = None, f"{first['type']}: {first['msg']}"
        if result.tokens_out >= client.config.num_predict:
            error += " (output was cut off at the num_predict limit)"

    return ExtractionResult(plan, False, error, result.tokens_out, result.tpot_ms, result.total_s)