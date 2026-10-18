# hub_speech_pipeline – Claude Code briefing

PC-side pipeline for **Component 1 (IT23264816, Gunathilaka K.K.N.M)** of project J26-SE-350:
*Real-Time Voice Capture, Transmission & Speech Processing Pipeline*. It picks up the speech
chunks that the Echo Vault phone app (`mobile_client/`) delivers over Syncthing and turns them
into timestamped transcripts (proposal §4.3, Stage 3 onwards). It is an individual research
deliverable, not shared team code.

## Working rules (non-negotiable)

1. Work only on branch `feature/c1-speech-pipeline`. Never commit, push, stage (`git add`),
   stash, reset, restore, checkout/switch branches, merge, rebase or clean. The developer
   reviews and commits everything manually. Read-only git (`status`, `diff`, `log`, `show`,
   `branch --show-current`) is fine. A local permission guard blocks the write commands; do not
   try to work around it (no `git -C`, `sh -c`, scripts or alternative invocations).
2. Only change files inside `hub_speech_pipeline/`. Logs and reports go in
   `hub_speech_pipeline/test_output/` (git-ignored). Anything outside this folder – other
   components, `mobile_client/`, `shared/`, `.github/`, root README, `.gitignore` – needs
   explicit approval first.
3. Ask before: adding or upgrading any dependency (conda or pip), downloading any model or
   dataset (state names, versions and sizes), or deleting files. When proposing a package,
   report: version, last release date, license, Windows/CPU support, maintenance status.
   Verify on the official index – do not rely on memory.
4. Data locations:
   - **Inputs are read-only:** `D:\SLIIT\Research\05 - Implementation\c1_inbox` (the
     Syncthing receive-only folder). Never create, modify, rename or delete anything there.
   - **Outputs:** `D:\SLIIT\Research\05 - Implementation\c1_outputs`.
5. Privacy (FR5, NFR4): no cloud services, analytics, crash reporting, telemetry or remote
   logging. **Models run offline**: they are downloaded once (after approval) into the local
   cache and then loaded with `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`; library telemetry
   is switched off (e.g. `PYANNOTE_METRICS_ENABLED=false`); the pipeline refuses non-loopback
   network connections. A missing model is a clear error, never a silent download.
6. Runtime: **CPU only**, in the **`c1-speech`** conda environment
   (`C:\Users\Nisal\miniconda3\envs\c1-speech`, Python 3.11). No GPU code paths.
7. Never fabricate results. Report only output of commands that were actually run. If a test
   fails or a step is incomplete, say so plainly. Label small or preliminary measurements as
   such.
8. Work step by step. After each step: stop, write the step report in `test_output/`, and wait
   for approval before starting the next step.

## Requirements this pipeline implements (from the proposal)

| ID | Requirement |
|---|---|
| FR4 | Consume the timestamped Opus chunks delivered over the LAN |
| FR5 / NFR4 | No external or cloud services; models offline |
| FR12 | Record processing timestamps to support latency measurement |
| NFR7 | No lost speech segments: every chunk the manifest lists is processed exactly once |

## Input contract (written by `mobile_client`, see `mobile_client/CLAUDE.md`)

- `c1_inbox/<session_id>/<session_id>_<seq:05d>.opus` (Ogg Opus, 16 kHz mono) and its sidecar
  `.json` (schema `c1-chunk/0.1`, with `sha256` of the `.opus`, `start_ms`/`end_ms` session
  offsets and `end_wallclock`).
- `<session_id>_manifest.json` (schema `c1-manifest/0.1`) lists every chunk. Syncthing does
  not preserve write order: a sidecar can arrive before its `.opus`, and the manifest before
  the last `.opus`.
- `end_wallclock` is phone time: latency needs the phone/PC clock offset (measured via adb,
  with its uncertainty).

## Code layout

```
hub_speech_pipeline/
  watchdog/   inbox polling, readiness rules, ordering, persistent state, session completion
  asr/        WhisperX engine (CPU, int8), model setup/check, transcripts, WER utility
  common/     offline enforcement (env, telemetry off, socket guard)
  tools/      verify_session.py (delivery checks, clock offset, latency)
  tests/      unit tests (stdlib unittest)
```

## Definition of done for every step

1. Unit tests pass: `python -m unittest discover -s hub_speech_pipeline -t .` (c1-speech env).
2. New logic has tests.
3. Step report in `hub_speech_pipeline/test_output/<step>_report.md`: files created or changed
   and why, commands run with their real output summary, test counts, measurements with their
   uncertainty, known limitations, open questions.
