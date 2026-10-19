"""Shared safety net for the MCP servers (RP-16).

FastMCP's own argument check writes the wrong value into its error text.
A value can come from a meeting transcript, so we replace that text with a
fixed code. Our own errors (reason codes only) pass through unchanged.
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.server.middleware import Middleware


class HideValidationDetails(Middleware):
    """Turn any argument-check error into the fixed code REJECTED:BAD_ARGUMENTS."""

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ValidationError:
            raise ToolError("REJECTED:BAD_ARGUMENTS") from None