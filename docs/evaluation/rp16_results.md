# RP-16 results

All numbers are from the project laptop: Windows 11, Python 3.12.4, FastMCP 4.1.1, 16 CPU threads, no GPU. Result files are in this folder.

## 1. Tests

At commit `dd6f602`: **274 passed, 1 skipped** (the skipped one is the official escape test, which runs only with `RUN_PT_SUITE=1`). RP-16 added 153 passing tests: sandbox 27, notes 21, filesystem server 16, calendar core 41, calendar server 19, orchestrator 10, latency script 4, vector dataset 5, escape harness 10.

## 2. Tool-call latency (NFR-01, target under 1.5 s per call)

Result file: `rp16_tool_latency_laptop.json`. 50 plans after 3 warm-up plans. Synthetic data, no LLM, in-memory calendar.

| Tool | Calls | Median | p95 | Max |
|---|---|---|---|---|
| `write_note` | 50 | 5.9 ms | 7.2 ms | 7.8 ms |
| `create_event` | 50 | 3.8 ms | 4.6 ms | 4.8 ms |

Starting both servers takes about 3.9 s, one time.

**Limits.** Google calls (network) are **not measured**. The 20 to 90 s LLM step is a different metric and is not part of this number. Passing here means the tool layer is fast, not that the whole pipeline is.

## 3. Sandbox escape test (target 0.0% under 50 vectors)

Result file: `rp16_path_traversal_results.json`. Dataset `agentic_core/datasets/path_traversal_vectors.json`, fingerprint `f32ddcd8...a449f5`, frozen in commit `7757b94` before the harness existed (`dd6f602`). The first full run is the official result.

**Result: 0 of 50 vectors escaped (0.0%).** 98 attempts (50 as folder, 48 as title). 49 blocked, 49 harmless, 0 rejected, 0 escape, 0 error, 0 not run.

Which defence stopped the 49 blocked attempts (from the result file):

| Stopped by | Count |
|---|---|
| Folder is not `Inbox`, `Meetings` or `Ideas` (`NOT_ALLOWED_DIR`) | 19 |
| Text rules: dot-dot, absolute path, drive or stream, null byte, reserved name, bad component, control character, empty component, too long | 28 |
| Filesystem checks (`OUTSIDE_ZONE`, `OUTSIDE_VAULT`, the 2 symlink vectors) | 2 |

The one folder vector that was not blocked, `PT-46` (`Ideas/..hidden`), is a legal folder name inside `Ideas`. The note was written inside the zone.

**Method.** A fresh temporary world per vector, with a canary file outside the vault. Phase 1 asks the guard where the note would go and checks the answer independently, so nothing is written if it would land outside. Phase 2 calls the real MCP tool and compares a snapshot of everything outside the three folders.

**Limits.**
- Zero failures in 50 tests only suggests a true failure rate below about 6% (rule of three). The vectors are not a random sample of all attacks.
- 10 strings follow public examples (OWASP, GitLab, ByteHide docs). 40 were composed by the author of the guard. They were not tuned on, but they are not independent of the author.
- Only 2 vectors reached the filesystem checks. Junctions and 8.3 short names are not covered.
- The title position is made safe before the guard runs, so it adds little evidence.
- The harness used the in-process MCP connection. The real stdio path was tested separately.

## 4. Not measured or not tested

- Google Calendar backend (not built, no credentials).
- Intent F1, JSON compliance over 200 prompts, TPOT, VRAM, SUS (other stories, GPU machine).
- Real meeting data end to end.