"""Small YAML header ("front matter") for vault notes (RP-18, section 2).

The orchestrator puts a header on top of every note it writes. The nightly
compaction job (RP-18, section 3) reads it back. Obsidian shows it as the
note's "Properties". No LLM here.

    ---
    type: note
    created: '2026-11-17T10:42:00+05:30'
    plan: 20261117-104200-3f2a
    synced_to_calendar: false
    ---
    # Title
    ...

yaml.safe_dump quotes any text that could be misread (dates, "true", ":"),
so text that came from the LLM can never break out of the header.
"""

from __future__ import annotations

import yaml

FENCE = "---"


def render(fields: dict) -> str:
    """Return the header block, ending with a newline."""
    body = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, default_flow_style=None)
    return f"{FENCE}\n{body}{FENCE}\n"


def split(text: str) -> tuple[dict | None, str]:
    """Split a note into (header, rest). Header is None if there is no valid one.

    Never raises: a broken header is treated as "no header", so one bad note
    can never stop the nightly job.
    """
    text = text.replace("\r\n", "\n")
    if not text.startswith(FENCE + "\n"):
        return None, text
    end = text.find("\n" + FENCE + "\n", len(FENCE))
    if end == -1:
        return None, text
    raw = text[len(FENCE) + 1 : end + 1]
    rest = text[end + len(FENCE) + 2 :]
    try:
        fields = yaml.safe_load(raw)
    except yaml.YAMLError:
        return None, text
    if not isinstance(fields, dict):
        return None, text
    return fields, rest
