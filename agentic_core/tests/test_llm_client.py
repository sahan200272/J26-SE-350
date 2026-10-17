"""Tests for the response_format option of LLMClient (RP-14). No Ollama needed."""
from types import SimpleNamespace

from agentic_core.llm.client import LLMClient


class FakeOllama:
    """Stands in for ollama.Client and remembers what it was asked."""

    def __init__(self):
        self.kwargs = None

    def chat(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            message=SimpleNamespace(content="{}"),
            eval_count=10,
            eval_duration=2_000_000_000,
            total_duration=3_000_000_000,
        )


def make_client():
    client = LLMClient()
    client._client = FakeOllama()
    return client


def test_schema_is_passed_to_ollama_as_format():
    client = make_client()
    schema = {"type": "object"}
    client.chat("hello", response_format=schema)
    assert client._client.kwargs["format"] == schema


def test_without_a_schema_format_is_none():
    client = make_client()
    client.chat("hello")
    assert client._client.kwargs["format"] is None


def test_result_numbers_are_still_calculated():
    result = make_client().chat("hello")
    assert result.tokens_out == 10
    assert result.tpot_ms == 200.0
    assert result.total_s == 3.0