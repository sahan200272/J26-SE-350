"""Digest writing for the filesystem MCP server (RP-18, section 1).

Writes one of the two nightly root files (todo.md, daily_brief.md).
Unlike notes, these files ARE overwritten every night, so the write is
atomic: write a temp file first, then swap it in with one os.replace.
A crash in the middle never leaves a half-written file. No MCP and no LLM here.
"""

from __future__ import annotations

import os
import tempfile

from .notes import MAX_CONTENT_CHARS, NoteError
from .sandbox import SandboxConfig, check_digest_path


def write_digest(config: SandboxConfig, name: str, content: str) -> str:
    """Create or replace one digest file. Returns its name relative to the vault.

    Raises SandboxViolation (bad name) or NoteError (bad content).
    """
    if not isinstance(content, str) or content.strip() == "":
        raise NoteError("EMPTY_CONTENT")
    if len(content) > MAX_CONTENT_CHARS:
        raise NoteError("CONTENT_TOO_LARGE")

    text = content.replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    try:
        data = text.encode("utf-8")  # encode BEFORE touching the disk
    except UnicodeEncodeError:
        raise NoteError("BAD_ENCODING") from None

    target = check_digest_path(config, name)

    # The temp file sits next to the target, so os.replace stays on one drive.
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".digest-", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)  # one step: old file or new file, never half
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return name
