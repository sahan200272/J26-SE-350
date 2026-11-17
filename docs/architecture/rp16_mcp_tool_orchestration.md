# RP-16: Tool-use orchestration via MCP

**Component:** 2, Agentic Reasoning Core. **Branch:** `feature/mcp-tool-orchestration`.
**Status:** built and tested for notes and calendar (in-memory calendar). The Google Calendar backend is **not built**.

## 1. What it does

RP-14 turns a meeting segment into an `ActionPlan` (notes and events). RP-16 performs that plan through two small MCP servers. The AI never touches the disk or the calendar directly. Each server has **one tool**, strict checks, and answers with short reason codes only. The orchestrator uses **no LLM**, only plain rules.

## 2. Picture

```
RP-14 ActionPlan (notes, events)
        |
        v
  Orchestrator  (agentic_core/mcp_servers/orchestrator.py, no LLM)
     |  MCP over stdio                 |  MCP over stdio
     v                                 v
  Filesystem server                 Calendar server
  tool: write_note                  tool: create_event
  notes.py + sandbox.py             core.py + config.py
     |                                 |
     v                                 v
  Vault: /Inbox /Meetings /Ideas    In-memory calendar
                                    (Google backend: not built)
```

## 3. Files

| File | Job |
|---|---|
| `mcp_servers/filesystem_server/sandbox.py` | The guard: text checks, then `resolve()` and `is_relative_to()` |
| `mcp_servers/filesystem_server/notes.py` | Builds a safe file name, writes a note, never overwrites |
| `mcp_servers/filesystem_server/server.py` | FastMCP server, tool `write_note` (and `write_digest`, added in RP-18) |
| `mcp_servers/calendar_server/config.py`, `config.yaml` | Settings: time zone `Asia/Colombo`, default duration, default reminder |
| `mcp_servers/calendar_server/core.py` | Checks input, builds the event, no duplicates, backend plug |
| `mcp_servers/calendar_server/server.py` | FastMCP server, one tool `create_event` |
| `mcp_servers/safe_errors.py` | Replaces FastMCP argument errors (which echo the input) with a fixed code |
| `mcp_servers/orchestrator.py` | Sends a plan to both servers, keeps them running, reports per item |
| `scripts/measure_tool_latency.py` | Measures tool-call speed (NFR-01) |
| `scripts/run_path_traversal_suite.py` | Runs the frozen 50-vector escape test |
| `datasets/path_traversal_vectors.json` | The frozen 50 vectors |

## 4. Rules

**Filesystem server**
- Only `write_note` (plus `write_digest` since RP-18: it can replace only `todo.md` and `daily_brief.md` in the vault root, see `rp18_nightly_compaction.md`). No read, list or delete tool.
- The folder must be exactly `Inbox`, `Meetings` or `Ideas`. Only `.md` files.
- The server builds the file name (`date_slug.md`) from the title. The AI never picks a path.
- An existing note is never overwritten (`-2`, `-3`, ...).
- Every blocked attempt is logged with a reason code (NFR-03).

**Calendar server**
- Only `create_event`. No read, edit or delete tool.
- Start time has no time zone. The settings file adds one (default `Asia/Colombo`).
- Same title (ignoring case and spaces) at the same start time is never created twice. The answer is `exists`.
- Reminder: pop-up before the start (default 10 minutes). Duration default 60 minutes.
- Attendees are names. They go into the description. **No invitation is ever sent.**

**Both servers**
- Errors are short codes only (`BLOCKED:...`, `REJECTED:...`, `BACKEND_ERROR`, `IO_ERROR`). A crash we did not expect is hidden from the caller.
- Logs go to stderr (stdout is the protocol channel).

**Orchestrator**
- Keeps both servers running for the whole session.
- One failing item never stops the others.
- The report holds no meeting text. Unknown error text becomes `TOOL_ERROR`.

## 5. Error codes in a report

`BLOCKED:*` (guard said no), `REJECTED:*` (input refused), `BACKEND_ERROR`, `IO_ERROR`, `TOOL_ERROR` (unknown text), `TRANSPORT_ERROR` (connection problem), `BAD_RESPONSE` (odd answer). The orchestrator itself can raise `CONNECT_FAILED` and `NOT_CONNECTED`.

## 6. Run

```powershell
.\.venv\Scripts\Activate.ps1
python -m agentic_core.mcp_servers.filesystem_server.server --vault <vault folder>
python -m agentic_core.mcp_servers.calendar_server.server --backend memory
python -m scripts.measure_tool_latency
python -m scripts.run_path_traversal_suite --out path_traversal_results.json
python -m pytest agentic_core/tests
```

## 7. Untuned guesses (not measured, may change)

Note slug 60 characters. Note content 100,000 characters. Up to 99 duplicate names. Relative path 200 characters. Event title 200 characters. 20 attendees, 100 characters each. Duration 5 to 1440 minutes. Reminder 0 to 1440 minutes. Default duration 60 minutes. Default reminder 10 minutes. Latency run: 3 warm-up plans, 50 measured plans.

## 8. Known limits

1. **Google backend not built.** The calendar is an in-memory fake. When a Google backend is added, event titles and times will leave the laptop. The "no cloud" claim then holds for audio, transcripts and notes, not for calendar events.
2. **Re-running a plan duplicates its notes** (`-2.md`). The calendar does not duplicate events. Stopping double processing belongs to the pipeline.
3. **Small gap between the check and the write.** Someone with local access could swap a folder for a symlink in that gap. Rated low risk for a single-user vault.
4. **Server logs can hold a short path** (up to 120 characters) of a blocked attempt, and a traceback for a disk error. The logs stay on the hub.
5. **Note names are `date_slug.md`.** Obsidian finds `[[Entity]]` links by exact file name, so Component 4's WikiLinks may need another naming mode. Open question for RP-15.
6. **Only `fastmcp` is pinned.** Its own dependencies can still change.
7. **The escape test used the in-process MCP connection.** The real stdio path was tested separately.