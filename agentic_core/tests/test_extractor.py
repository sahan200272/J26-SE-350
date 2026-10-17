"""Tests for the extractor (RP-14, section 4). A fake client is used, so no LLM runs."""
from datetime import date
from types import SimpleNamespace

from agentic_core.decoding.extractor import SYSTEM_PROMPT, build_user_prompt, extract_plan
from agentic_core.decoding.plan_schema import ActionPlan
from agentic_core.llm.client import LLMResult
from agentic_core.segmentation.segmenter import Segment
from agentic_core.segmentation.transcript import Turn

MONDAY = date(2026, 10, 12)
GOOD_REPLY = (
    '{"actions":[{"method":"create_calendar_event",'
    '"title":"Demo","start":"2026-10-16T10:00:00"}]}'
)


class FakeClient:
    """Returns a prepared answer and remembers how it was called."""

    def __init__(self, text, tokens_out=20, num_predict=512):
        self.text = text
        self.tokens_out = tokens_out
        self.config = SimpleNamespace(num_predict=num_predict)
        self.calls = []

    def chat(self, user_prompt, system_prompt=None, response_format=None):
        self.calls.append((user_prompt, system_prompt, response_format))
        return LLMResult(self.text, self.tokens_out, 200.0, 4.0)


def make_segment(*texts):
    turns = tuple(
        Turn(start_s=630.0 + i, speaker="Speaker 1", text=text, line_no=i + 1)
        for i, text in enumerate(texts)
    )
    return Segment(0, turns, "start", 10, False)


def test_valid_answer_gives_a_plan_and_keeps_the_numbers():
    client = FakeClient(GOOD_REPLY)
    result = extract_plan(make_segment("I will book the demo for Friday at ten o'clock."), client, MONDAY)
    assert result.plan is not None and result.plan.actions[0].title == "Demo"
    assert (result.skipped, result.error) == (False, None)
    assert (result.tokens_out, result.tpot_ms, result.total_s) == (20, 200.0, 4.0)


def test_chatter_is_reported_not_crashed():
    client = FakeClient("Sure! Here is the plan you asked for.")
    result = extract_plan(make_segment("Please remind Kasun."), client, MONDAY)
    assert result.plan is None
    assert result.error.startswith("json_invalid")
    assert "Kasun" not in result.error      # the error must not leak transcript text


def test_rule_failure_after_valid_json_is_reported():
    client = FakeClient('{"actions":[{"method":"create_note","title":"x"}]}')
    result = extract_plan(make_segment("Please note this."), client, MONDAY)
    assert result.plan is None and "body" in result.error


def test_small_talk_never_reaches_the_llm():
    client = FakeClient(GOOD_REPLY)
    result = extract_plan(make_segment("Nice weather."), client, MONDAY)
    assert client.calls == []
    assert result.skipped is True and result.plan == ActionPlan(actions=[])


def test_prefilter_can_be_switched_off():
    client = FakeClient('{"actions":[]}')
    result = extract_plan(make_segment("Nice weather."), client, MONDAY, use_prefilter=False)
    assert len(client.calls) == 1 and result.skipped is False


def test_schema_and_system_prompt_are_sent():
    client = FakeClient(GOOD_REPLY)
    extract_plan(make_segment("Please remind Kasun."), client, MONDAY)
    _, system_prompt, response_format = client.calls[0]
    assert system_prompt == SYSTEM_PROMPT
    assert response_format == ActionPlan.model_json_schema()


def test_prompt_has_date_and_weekday_but_no_timestamps():
    prompt = build_user_prompt(make_segment("Hello there."), MONDAY)
    assert "2026-10-12 (Monday)" in prompt
    assert "Speaker 1: Hello there." in prompt
    assert "00:10:30" not in prompt


def test_cut_off_output_is_explained():
    client = FakeClient('{"actions":[{"method"', tokens_out=512, num_predict=512)
    result = extract_plan(make_segment("Please remind Kasun."), client, MONDAY)
    assert result.plan is None and "cut off" in result.error