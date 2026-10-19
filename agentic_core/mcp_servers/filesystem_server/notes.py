"""Note writing for the filesystem MCP server (RP-16, section 2a).

The file name is built by code from the title. The LLM never picks a path.
An existing note is never overwritten. No MCP and no LLM in this file.
"""

from __future__ import annotations

import unicodedata
from datetime import date

from .sandbox import SandboxConfig, check_path

# Untuned guesses.
MAX_SLUG_CHARS = 60
MAX_CONTENT_CHARS = 100_000
MAX_DUPLICATES = 99


class NoteError(Exception):
    """A note could not be written. The message is only a reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def make_slug(title: str) -> str:
    """Turn a title into a safe file-name part.

    Keeps letters, digits and combining marks (needed for Sinhala/Tamil).
    Everything else becomes one dash.
    """
    text = unicodedata.normalize("NFKC", title).casefold()
    pieces: list[str] = []
    last_was_dash = True  # stops a leading dash
    for ch in text:
        if unicodedata.category(ch)[0] in ("L", "N", "M"):
            pieces.append(ch)
            last_was_dash = False
        elif not last_was_dash:
            pieces.append("-")
            last_was_dash = True
    slug = "".join(pieces)[:MAX_SLUG_CHARS].strip("-")
    return slug or "untitled"


def write_note(
    config: SandboxConfig,
    folder: str,
    title: str,
    content: str,
    *,
    today: date | None = None,
) -> str:
    """Write one new note. Returns its path relative to the vault.

    Raises SandboxViolation (bad path) or NoteError (bad content).
    """
    if not isinstance(title, str):
        raise NoteError("BAD_TITLE")
    if not isinstance(content, str) or content.strip() == "":
        raise NoteError("EMPTY_CONTENT")
    if len(content) > MAX_CONTENT_CHARS:
        raise NoteError("CONTENT_TOO_LARGE")

    text = content.replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    try:
        data = text.encode("utf-8")  # encode BEFORE creating the file
    except UnicodeEncodeError:
        raise NoteError("BAD_ENCODING") from None

    stamp = (today or date.today()).isoformat()
    slug = make_slug(title)

    for attempt in range(1, MAX_DUPLICATES + 2):
        suffix = "" if attempt == 1 else f"-{attempt}"
        relative = f"{folder}/{stamp}_{slug}{suffix}.md"
        target = check_path(config, relative)  # the guard from section 1
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(target, "xb") as handle:  # "x" = fail if it already exists
                handle.write(data)
        except FileExistsError:
            continue
        return relative

    raise NoteError("TOO_MANY_DUPLICATES")