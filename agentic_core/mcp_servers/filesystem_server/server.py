"""FastMCP filesystem server (RP-16, section 2b).

One tool only: write_note. There is no read, list, delete or overwrite tool,
so the AI cannot do more than the sandbox rules allow.

Run from the repo root:
    python -m agentic_core.mcp_servers.filesystem_server.server --vault <folder>

stdout is the protocol channel (stdio), so all logs go to stderr.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..safe_errors import HideValidationDetails
from .notes import NoteError
from .notes import write_note as _write_note
from .sandbox import SandboxConfig, SandboxViolation

logger = logging.getLogger("agentic_core.filesystem_server")

INSTRUCTIONS = (
    "Writes new Markdown notes into a sandboxed vault. "
    "Allowed folders: Inbox, Meetings, Ideas. Existing notes are never changed."
)


def create_server(config: SandboxConfig) -> FastMCP:
    """Build the server. Kept as a function so tests can use it without stdio."""
    # mask_error_details: an unexpected crash never leaks paths or stack text.
    # Our own ToolError messages (reason codes only) still reach the client.
    mcp = FastMCP(
        name="vault-filesystem",
        instructions=INSTRUCTIONS,
        mask_error_details=True,
        middleware=[HideValidationDetails()],
    )

    @mcp.tool(name="write_note")
    def write_note(folder: str, title: str, content: str) -> dict:
        """Create one new Markdown note.

        folder: Inbox, Meetings or Ideas.
        title: used to build the file name (the server chooses the real name).
        content: the Markdown text of the note.
        Returns the path of the new note, relative to the vault.
        """
        try:
            relative = _write_note(config, folder, title, content)
        except SandboxViolation as violation:
            raise ToolError(f"BLOCKED:{violation.reason}") from None
        except NoteError as error:
            raise ToolError(f"REJECTED:{error.reason}") from None
        except OSError:
            logger.exception("write failed")  # details go to the log, not the client
            raise ToolError("IO_ERROR") from None
        return {"path": relative}

    return mcp


def _setup_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Sandboxed vault filesystem MCP server")
    parser.add_argument("--vault", required=True, type=Path, help="path to the vault folder")
    parser.add_argument("--log-file", type=Path, default=None, help="also write the log here")
    args = parser.parse_args(argv)

    vault = args.vault.expanduser().resolve()
    if not vault.is_dir():
        parser.error("the vault folder does not exist")

    _setup_logging(args.log_file)
    server = create_server(SandboxConfig(vault_root=vault))
    server.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()