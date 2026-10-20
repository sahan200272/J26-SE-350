"""Frozen hashes of SYSTEM_PROMPT, the DraftPlan schema and the LLM config (NFR-04).

None means "not frozen yet": any run is then marked not official.
Set these once, just before the official run, in their own commit.
"""

FROZEN_SETUP_HASHES: dict[str, str] | None = None
