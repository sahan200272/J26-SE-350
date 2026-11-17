# Agentic Core

**Purpose:** Provide local-first, privacy-preserving reasoning and tool orchestration.

**Owner:** TBD

The agentic core uses a quantized LLaMA 3 8B model via Ollama, with
grammar-constrained JSON-RPC 2.0 decoding. It includes a FastMCP zero-trust
filesystem sandbox whose writes are confined to `/Inbox`, `/Meetings`, and
`/Ideas`, plus a Google Calendar MCP server. A nightly 8:00 PM compaction job
produces `todo.md` and `daily_brief.md`.

## Setup

## Testing

## Nightly compaction (RP-18)

Rules only, no LLM. Reads the vault and writes `todo.md` and `daily_brief.md`
through the filesystem MCP tool `write_digest`.

```powershell
python -m agentic_core.compaction.run --vault <vault folder> --dry-run
```

Scheduler, rules and results: `docs/architecture/rp18_nightly_compaction.md`.
