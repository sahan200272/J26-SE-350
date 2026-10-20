"""Frozen hashes of SYSTEM_PROMPT, the DraftPlan schema and the LLM config (NFR-04).

Frozen after the first dev run, before the official run. Decision: no prompt,
schema or config fix; the current design is measured as it is.
If any of these change, the runner stops with exit code 2.
"""

FROZEN_SETUP_HASHES: dict[str, str] | None = {
    "system_prompt": "c02aa2d5ae6ce204dcbd4cecf7ca31a0510f940135f35c795b2e61a7b6313a15",
    "draft_schema": "e492b95a17549ba12810e558de6ab700a44ae0d41bc1ade25ea4e242af50524a",
    "llm_config": "53386c8ac861e93064b7e48b97b81c99ad90be117d18b157acbb89818510bcb2",
}
