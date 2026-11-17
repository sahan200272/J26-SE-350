# RP-18: Headless nightly compaction (todo.md, daily_brief.md)

**Component:** 2, Agentic Reasoning Core. **Branch:** `feature/nightly-compaction`.
**Status:** built and tested. Rules only, **no LLM**. The Google Calendar backend is still **not built** (in-memory fake), so `synced_to_calendar` reflects the fake calendar.

## 1. What it does

Every evening at **20:00** (blueprint: 8:00 PM) a scheduler starts one Python program. It reads the notes of the last days, finds tasks and meetings, joins what belongs together across conversations, and **overwrites two files in the vault root**:

- `todo.md`: a prioritised checklist (do first, soon, later), meetings that are NOT in the calendar, and the meetings of the next 7 days.
- `daily_brief.md`: a short summary of the last 24 hours (counts, meetings, notes by folder, tasks done, what needs attention).

Every line links back to its source note with an Obsidian `[[link]]`.

## 2. Picture

```
 cron 20:00 (Linux hub)          Task Scheduler 20:00 (Windows, development)
   run_compaction.sh                 run_compaction.ps1        <- wrappers, no logic
            \                          /
             v                        v
     python -m agentic_core.compaction.run --vault <vault>
        |  collect.py  read only, every path through check_path (sandbox guard)
        |  rules.py    tasks, cross-session merge, calendar flag, priority (no LLM)
        |  render.py   Markdown text
        v
   MCP over stdio -> filesystem server -> tool write_digest
                                          (only todo.md / daily_brief.md, vault root,
                                           atomic replace)
```

## 3. Files

| File | Job |
|---|---|
| `mcp_servers/filesystem_server/digest.py` | Atomic overwrite of the two root files (temp file + `os.replace`) |
| `mcp_servers/filesystem_server/sandbox.py` | New `check_digest_path`: exact-name allowlist, vault root only |
| `mcp_servers/filesystem_server/server.py` | New tool `write_digest` (now 2 tools; still no read/list/delete) |
| `mcp_servers/note_header.py` | YAML header on every note (`type`, `created`, `plan`, `synced_to_calendar`) |
| `mcp_servers/orchestrator.py` | Adds the header; writes one record note per event in `Meetings/` |
| `compaction/config.py`, `config.yaml` | Settings (all untuned guesses) |
| `compaction/collect.py` | Reads the vault (read only, guarded) |
| `compaction/rules.py` | The rules (below) |
| `compaction/render.py` | Builds the two Markdown files |
| `compaction/run.py` | Entry point; writes through MCP `write_digest` |
| `scripts/scheduler/run_compaction.sh`, `compaction.cron` | Linux hub scheduler |
| `scripts/scheduler/run_compaction.ps1`, `compaction_task.xml` | Windows Task Scheduler (development) |

## 4. The note header (input data contract inside Component 2)

```yaml
---
type: note            # or: event
created: '2026-11-17T10:42:00+05:30'
plan: 20261117-104200-3f2a   # same id for all notes and events of one conversation
synced_to_calendar: false
# events only:
start: '2026-11-18T09:30'
attendees: [Alice, Kasun]
calendar_status: created     # created, exists or failed
---
```

`yaml.safe_dump` quotes text that could be misread, so LLM text cannot break out of the header (tested). Notes without a header (written by hand) still work: their time is the file's change time. `shared/schemas/` is **not** changed.

## 5. Rules (no LLM)

**Tasks:** `- [ ] text` (open) and `- [x] text` (done) lines in any note. An Inbox note with no checkbox is one reminder (its title).

**Cross-session rules** (a session = one plan = one conversation):
1. Same words (case, spaces, punctuation ignored) = one task. First seen, last seen and mention count are kept.
2. The latest mention wins: `[x]` closes, a later `[ ]` opens again.
3. A task whose words contain an event title is **scheduled** (handled) if that event has `synced_to_calendar: true`. A task from the same plan as exactly one event is only **linked** to it (raises priority; the meeting being booked does not mean the task is done).
4. An open task first seen before today's 24-hour window is **carried over**.
5. Re-run copies of one event (same title and start) are merged.

**Priority** (untuned guesses, in `config.yaml`):
1. urgent word (`urgent`, `asap`, `today`, ...), or linked meeting in the next 24 hours
2. carried over 3+ days, or mentioned 2+ times
3. everything else

Events with `synced_to_calendar: false` get their own section at the top of `todo.md`: "Add to your calendar by hand".

## 6. Safety

- **Writes:** only through the MCP tool `write_digest`. Names other than `todo.md` / `daily_brief.md` are blocked (`NOT_ALLOWED_DIGEST`); a planted shortcut is blocked (`OUTSIDE_VAULT`); `write_note` still cannot reach the root.
- **Reads:** every file path goes through `check_path`, so a shortcut out of the vault is skipped (`BLOCKED`), never read. Files over 100,000 characters are skipped.
- **Atomic:** a crash during the write leaves the old file, never half a file (tested).
- **Privacy:** the log has counts and reason codes only, never note text (tested). Note text in the output is cut to one line, and `[[`/`]]` are broken up, so a note cannot add headings or fake links.

## 7. Scheduler

The job is a plain Python entry point (testable on Windows). The schedulers only start it.

**Linux hub (cron):** edit the two paths in `scripts/scheduler/compaction.cron`, then `crontab -e` and paste the lines. `CRON_TZ=Asia/Colombo` keeps 20:00 in Sri Lanka time. Cron does **not** catch up a missed run (hub off at 20:00); the hub is expected to be always on.

**Windows (development):** replace `REPO_PATH` and `VAULT_PATH` in `scripts/scheduler/compaction_task.xml`, then:

```powershell
Register-ScheduledTask -TaskName "J26 nightly compaction" -Xml (Get-Content -Raw scripts\scheduler\compaction_task.xml)
Start-ScheduledTask -TaskName "J26 nightly compaction"      # run once now to test
Get-ScheduledTaskInfo -TaskName "J26 nightly compaction"     # LastTaskResult 0 = ok
```

`StartWhenAvailable` runs the job when the laptop wakes if it was asleep at 20:00. `IgnoreNew` stops two runs at once.

**Run by hand:**

```powershell
python -m agentic_core.compaction.run --vault <vault> --dry-run                  # print, write nothing
python -m agentic_core.compaction.run --vault <vault>                            # write both files
python -m agentic_core.compaction.run --vault <vault> --now 2026-11-17T20:00     # pretend time
```

Exit codes: `0` both files written, `1` a write failed, `2` bad input or settings. Log: `logs/compaction.log` (ignored by git).

## 8. Results

| Check | Result | Where |
|---|---|---|
| Unit and integration tests | 666 passed, 1 skipped | tested on Laptop 1 (Windows 11, Python 3.12.4) |
| Frozen 50 path-traversal vectors after adding `write_digest` | 0/50 escapes, fingerprint `f32ddcd8...` unchanged | tested on Laptop 1, `docs/evaluation/rp18_path_traversal_recheck.json` |
| 12 new `write_digest` escape vectors | 12/12 blocked, nothing written | tested on Laptop 1 (pytest) |
| Tool latency (50 plans, now 2 `write_note` per plan) | `write_note` max 8.0 ms, `create_event` max 5.7 ms (target < 1500 ms) | tested on Laptop 1, `docs/evaluation/rp18_tool_latency_laptop.json` |
| Compaction speed, 1,200 synthetic notes | about 0.7 s | checked in sandbox (Linux), untuned, not an official number |
| SUS >= 75 for daily compaction | **not measured yet**: needs user trials | open |

All test data is synthetic. No tuning data and no evaluation data were used.

## 9. Known limits

- Task detection is by checkbox lines and Inbox notes only. Free-text tasks inside a note body ("Kasun will send the slides") are not found unless RP-14 writes them as `- [ ]` lines. Possible later step: ask the LLM only for notes with no checkbox (speed trade-off: 20 to 90 s per call on Laptop 1 CPU).
- The title match for "scheduled" is a word-subset rule (untuned). A task and a meeting with different words are not joined unless they share a plan id.
- `synced_to_calendar` reflects the in-memory calendar until the Google backend is built.
- Ticks made in `todo.md` itself are lost at the next run (the file says so); ticks belong in the source note.
- A re-run of the same plan still makes `-2` copies of notes (RP-16 limit); events are merged by rule 5, tasks by rule 1.
