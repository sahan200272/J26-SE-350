"""FastMCP calendar server (RP-16, section 3b).

One tool only: create_event. No read, list, edit or delete tool, and no
invitation is ever sent (attendees are names that go into the description).

Run from the repo root:
    python -m agentic_core.mcp_servers.calendar_server.server --backend memory

stdout is the protocol channel (stdio), so all logs go to stderr.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..safe_errors import HideValidationDetails
from .config import CalendarConfig, ConfigError, load_config
from .core import BackendError, CalendarBackend, CalendarError, InMemoryCalendar
from .core import create_event as _create_event

logger = logging.getLogger("agentic_core.calendar_server")

INSTRUCTIONS = (
    "Creates calendar events with a pop-up reminder. "
    "Times are local (no time zone); the server adds the configured zone. "
    "The same title at the same start time is never created twice."
)


def create_server(backend: CalendarBackend, config: CalendarConfig) -> FastMCP:
    """Build the server. Kept as a function so tests can use it without stdio."""
    mcp = FastMCP(
        name="vault-calendar",
        instructions=INSTRUCTIONS,
        mask_error_details=True,
        middleware=[HideValidationDetails()],
    )

    # duration_minutes and reminder_minutes are typed Any on purpose: FastMCP would
    # quietly turn True into 1 and "60" into 60. Our own strict check refuses them.
    @mcp.tool(name="create_event")
    def create_event(
        title: str,
        start: str,
        attendees: list[str] | None = None,
        duration_minutes: Any = None,
        reminder_minutes: Any = None,
    ) -> dict:
        """Create one calendar event, or return the existing one.

        title: the event name.
        start: local start time, ISO format without a time zone, e.g. 2026-10-19T15:00.
        attendees: names only. They go into the description. No invitation is sent.
        duration_minutes: whole number. Default comes from the settings file.
        reminder_minutes: whole number of minutes before the start. Default from settings.
        Returns status ("created" or "exists"), event_id, start, end, reminder_minutes.
        """
        try:
            result = _create_event(
                backend,
                config,
                title=title,
                start=start,
                attendees=attendees,
                duration_minutes=duration_minutes,
                reminder_minutes=reminder_minutes,
            )
        except CalendarError as error:
            raise ToolError(f"REJECTED:{error.reason}") from None
        except BackendError as error:
            logger.error("calendar backend failed: %s", error.reason)
            raise ToolError("BACKEND_ERROR") from None
        except Exception as error:  # a crash we did not expect: log the class only
            logger.error("calendar crashed: %s", type(error).__name__)
            raise ToolError("BACKEND_ERROR") from None
        event = result.event
        return {
            "status": result.status,
            "event_id": event.event_id,
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
            "reminder_minutes": event.reminder_minutes,
        }

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
    parser = argparse.ArgumentParser(description="Calendar MCP server")
    parser.add_argument(
        "--backend",
        required=True,
        choices=["memory"],
        help="memory = dry run, nothing is saved",
    )
    parser.add_argument("--config", type=Path, default=None, help="settings file (YAML)")
    parser.add_argument("--log-file", type=Path, default=None, help="also write the log here")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as error:
        parser.error(str(error))

    _setup_logging(args.log_file)
    backend: CalendarBackend = InMemoryCalendar()
    logger.warning("memory backend: this is a dry run, no event is saved anywhere")
    create_server(backend, config).run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()