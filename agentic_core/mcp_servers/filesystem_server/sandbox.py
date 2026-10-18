"""Path guard for the filesystem MCP server (RP-16, section 1).

Gives one answer per path: a safe full path, or a SandboxViolation with a
short reason code. It never touches the disk except to resolve the path.
No LLM is used here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("agentic_core.sandbox")

# Folders inside the vault where writes are allowed (blueprint, Stage 2).
ALLOWED_DIRS = ("Inbox", "Meetings", "Ideas")
# Only Markdown notes. Design choice, easy to change.
ALLOWED_SUFFIXES = (".md",)
# Untuned guess: a safe upper limit for a relative path.
MAX_PATH_CHARS = 200

# Names Windows treats as devices, not files.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class SandboxViolation(Exception):
    """Raised when a path is not allowed. The message is only a reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SandboxConfig:
    vault_root: Path
    allowed_dirs: tuple[str, ...] = ALLOWED_DIRS
    allowed_suffixes: tuple[str, ...] = ALLOWED_SUFFIXES
    max_path_chars: int = MAX_PATH_CHARS


def check_path(config: SandboxConfig, relative_path: object) -> Path:
    """Return the safe full path, or raise SandboxViolation.

    Every blocked attempt is written to the security log.
    """
    try:
        return _check(config, relative_path)
    except SandboxViolation as violation:
        logger.warning(
            "sandbox violation reason=%s path=%r",
            violation.reason,
            str(relative_path)[:120],
        )
        raise


def _check(config: SandboxConfig, relative_path: object) -> Path:
    # ---- Layer 1: look at the text before touching the disk ----
    if not isinstance(relative_path, str):
        raise SandboxViolation("NOT_TEXT")
    if relative_path.strip() == "":
        raise SandboxViolation("EMPTY")
    if len(relative_path) > config.max_path_chars:
        raise SandboxViolation("TOO_LONG")
    if "\x00" in relative_path:
        raise SandboxViolation("NULL_BYTE")
    if any(ord(ch) < 32 for ch in relative_path):
        raise SandboxViolation("CONTROL_CHAR")

    # Treat backslash like slash, so Windows and Linux see the same thing.
    text = relative_path.replace("\\", "/")

    if text.startswith("/"):
        raise SandboxViolation("ABSOLUTE")
    if ":" in text:  # drive letters (C:) and Windows data streams (a.md:x)
        raise SandboxViolation("DRIVE_OR_STREAM")

    parts = text.split("/")
    if "" in parts:  # double slash or trailing slash
        raise SandboxViolation("EMPTY_COMPONENT")
    for part in parts:
        if part in (".", ".."):
            raise SandboxViolation("TRAVERSAL")
        if part != part.rstrip(" ."):  # Windows silently drops trailing dot/space
            raise SandboxViolation("BAD_COMPONENT")
        if part.split(".")[0].upper() in _WINDOWS_RESERVED:
            raise SandboxViolation("RESERVED_NAME")

    # A note must sit inside an allowed folder, never in the vault root.
    if len(parts) < 2 or parts[0] not in config.allowed_dirs:
        raise SandboxViolation("NOT_ALLOWED_DIR")
    if not text.lower().endswith(config.allowed_suffixes):
        raise SandboxViolation("BAD_SUFFIX")

    # ---- Layer 2: ask where the path REALLY ends up ----
    root = config.vault_root.resolve()
    zone = (root / parts[0]).resolve()  # follows shortcuts (symlinks)
    target = root.joinpath(*parts).resolve()

    if not zone.is_relative_to(root):  # the allowed folder itself is a shortcut out
        raise SandboxViolation("OUTSIDE_VAULT")
    if not target.is_relative_to(zone):
        raise SandboxViolation("OUTSIDE_ZONE")

    return target