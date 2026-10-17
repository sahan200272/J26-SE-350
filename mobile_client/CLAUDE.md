# mobile_client – Claude Code briefing

Android Flutter client for **Component 1 (IT23264816, Gunathilaka K.K.N.M)** of project
J26-SE-350: *Real-Time Voice Capture, Transmission & Speech Processing Pipeline*.
This app is the **Edge Capture Layer** and the start of the **Local Transmission Layer**
(proposal §4.3, Stages 1–2). It is an individual research deliverable, not shared team code.

## Working rules (non-negotiable)

1. Work only on branch `feature/c1-speech-pipeline`. Never commit, push, stage (`git add`),
   stash, reset, restore, checkout/switch branches, merge, rebase or clean. The developer
   reviews and commits everything manually. Read-only git (`status`, `diff`, `log`, `show`,
   `branch --show-current`) is fine. A local permission guard blocks the write commands; do not
   try to work around it (no `git -C`, `sh -c`, scripts or alternative invocations).
2. Only change files inside `mobile_client/`. Logs/reports may go in `mobile_client/test_output/`
   (git-ignored). Anything outside this folder – other components, `shared/`, `.github/`,
   root README, `.gitignore` – needs explicit approval first.
3. Ask before: adding or upgrading any dependency, changing `android/` build config
   (Gradle, minSdk/targetSdk, signing), adding Android permissions, or deleting files.
   When proposing a package, report: version, last publish date, license, Android support,
   maintenance status. Verify on pub.dev – do not rely on memory.
4. Android only. Do not add or generate iOS, web, desktop or macOS support.
5. Privacy (FR5, NFR4): no cloud services, Firebase, analytics, crash reporting, telemetry or
   remote logging. Audio never leaves the device except via the Syncthing-shared folder.
   Design decision: the **main** `AndroidManifest.xml` must not declare `INTERNET`
   (the debug/profile manifests created by Flutter may keep it for tooling).
6. Never fabricate results. Report only output of commands that were actually run.
   If a test fails or a step is incomplete, say so plainly.
7. Work in the step order below. After each step: stop, write the step report, and wait
   for approval before starting the next step.

## Requirements this app implements (from the proposal)

| ID | Requirement |
|---|---|
| FR1 | Start/stop capture only by explicit user action; visible recording indicator while recording |
| FR2 | Pause/resume; **no audio captured while paused** |
| FR3 | VAD identifies speech regions; non-speech excluded from further processing |
| FR4 | Speech divided into timestamped compressed (Opus) chunks, transferred over the LAN |
| FR5 / NFR4 | No external or cloud services |
| FR12 | Record processing timestamps to support latency measurement |
| NFR7 | No lost speech segments: every detected segment must be accounted for |

Not continuous listening: there is no wake word and no background always-on capture.

## Audio and data conventions

- Internal audio: 16 kHz, mono, 16-bit PCM (Whisper/WhisperX input format).
- VAD sits behind one interface with interchangeable implementations:
  `EnergyVad` (baseline: energy threshold + fixed-duration chunking, proposal Table 5) and a
  neural VAD (proposed approach). VAD and segmentation logic must be **pure Dart with no
  Flutter imports**, so it can be unit-tested and run offline on WAV files for evaluation
  (VAD precision/recall/F1 on AMI, SO1/NFR5).
- Chunk files: `<session_id>_<seq:05d>.opus` plus a sidecar `<session_id>_<seq:05d>.json`.
  `session_id` = local start time + short random suffix, e.g. `20261014T142300_a1b2`.
- Sidecar fields (schema_version `c1-chunk/0.1`): `schema_version`, `session_id`, `seq`,
  `audio_file`, `codec`, `sample_rate`, `channels`, `start_ms`, `end_ms` (offsets from session
  start on a monotonic clock), `start_wallclock`, `end_wallclock` (ISO 8601 with ms and UTC
  offset), `duration_ms`, `vad` (`type` + parameters), `app_version`, `sha256` of the audio file.
  No device identifiers, names or location.
- Session manifest `<session_id>_manifest.json` written on stop: chunk count, list of seqs,
  pause intervals, session start/end. Lets the PC detect missing chunks (NFR7).
- Write each file to app-private storage first, then move it into the synced folder in one
  rename, so Syncthing and the PC watchdog never see partial files.
- `end_wallclock` is needed later for latency (end of utterance → structured output, proposal
  Appendix B). Phone/PC clock offset must be accounted for in the PC-side measurement.

## Suggested code layout

```
lib/
  main.dart
  ui/            recording screen, indicator, timer
  session/       session state machine: idle → recording ⇄ paused → stopped
  capture/       microphone PCM stream wrapper (behind an interface for tests)
  vad/           Vad interface, EnergyVad, neural VAD (pure Dart)
  segmentation/  frames + VAD decisions → timestamped speech segments (pure Dart)
  encoding/      Opus encoder wrapper
  transfer/      chunk + sidecar + manifest writer for the Syncthing folder
test/            unit + widget tests mirroring lib/
```

## Step plan (PP1 on 2026-10-20)

- **A1** Project scaffold (Android only), session state machine, recording screen with
  Start/Pause/Resume/Stop, visible indicator and timer, microphone permission handling.
  Plus a read-only package survey for PCM capture, Opus encoding and neural VAD.
- **A2** Live 16 kHz mono PCM capture wired to the state machine (FR2 enforced).
- **A3** EnergyVad baseline + segmenter (pure Dart) with unit tests; neural VAD if feasible.
- **A4** Opus encoding of segments + sidecar metadata + manifest.
- **A5** Delivery into the Syncthing-shared folder; verify arrival on the PC with no gaps.

## Definition of done for every step

1. `flutter analyze` – no errors or warnings introduced.
2. `flutter test` – all tests pass; new logic has tests.
3. `flutter build apk --debug` succeeds.
4. Step report written to `mobile_client/test_output/<step>_report.md` with: files created or
   changed and why, commands run with their real output summary, test counts, manual checks
   the developer still needs to do on the phone, known limitations, open questions.
