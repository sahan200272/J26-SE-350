"""The prompt, the schema sent to Ollama and the LLM config must not change after the setup freeze (NFR-04)."""

from agentic_core.tests.schema_compliance.frozen_setup import FROZEN_SETUP_HASHES
from agentic_core.tests.schema_compliance.harness import setup_hashes


def test_setup_is_frozen():
    assert FROZEN_SETUP_HASHES is not None


def test_prompt_schema_and_config_are_unchanged_since_the_setup_freeze():
    assert setup_hashes() == FROZEN_SETUP_HASHES
