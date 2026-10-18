"""Run the hub: watch the inbox and transcribe chunks as they become ready.

    python -m hub_speech_pipeline.watchdog --model base --serial <adb serial> [--until-idle]

Outputs go to ``<outputs>/whisperx-<model>-<compute_type>/`` (per-session folders, state.json,
run summaries). The inbox is only read. The phone/PC clock offset is measured over adb at start
(and every ``--clock-refresh-min`` minutes while running) for the latency correction.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

DEFAULT_INBOX = Path(r"D:\SLIIT\Research\05 - Implementation\c1_inbox")
DEFAULT_OUTPUTS = Path(r"D:\SLIIT\Research\05 - Implementation\c1_outputs")


class ClockTracker:
    """Latest phone - PC offset from adb; None when no phone is given."""

    def __init__(self, serial: str | None, refresh_s: float, log):
        self.serial, self.refresh_s, self.log = serial, refresh_s, log
        self.measurements: list[dict] = []
        self._last = 0.0
        if serial:
            self.measure()

    def measure(self) -> None:
        from hub_speech_pipeline.tools.verify_session import measure_clock

        m = measure_clock(self.serial, samples=30)
        self.measurements.append(m)
        self._last = time.monotonic()
        self.log(f"[clock] phone - PC offset {m['offset_ms']:.2f} ms +/- {m['uncertainty_ms']:.2f} ms "
                 f"(tightest round trip {m['best_rtt_ms']:.1f} ms, {m['samples']} samples)")

    def __call__(self) -> dict | None:
        if not self.serial:
            return None
        if time.monotonic() - self._last > self.refresh_s:
            self.measure()
        return self.measurements[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="base", choices=["base", "small"])
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--outputs", type=Path, default=DEFAULT_OUTPUTS)
    parser.add_argument("--serial", help="adb serial of the phone, for the clock offset")
    parser.add_argument("--clock-refresh-min", type=float, default=10)
    parser.add_argument("--interval-ms", type=float, default=200)
    parser.add_argument("--until-idle", action="store_true", help="exit once every session is complete")
    parser.add_argument("--exit-after-sessions", type=int, metavar="N",
                        help="live mode: exit after N sessions that were not complete at start have completed")
    parser.add_argument("--max-minutes", type=float, help="exit after this many minutes in any case")
    parser.add_argument("--session", action="append", help="only these session IDs")
    args = parser.parse_args(argv)

    # Offline first, before anything imports whisperx / huggingface_hub / pyannote.
    from hub_speech_pipeline.common.offline import blocked_attempts, enforce_offline

    offline_env = enforce_offline()
    from hub_speech_pipeline.asr.engine import WhisperXEngine
    from hub_speech_pipeline.asr.models import ModelMissingError
    from hub_speech_pipeline.watchdog.watchdog import Watchdog

    log = lambda message: print(f"{dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]} {message}", flush=True)  # noqa: E731
    outputs = args.outputs / f"whisperx-{args.model}-{args.compute_type}"
    started = dt.datetime.now().astimezone()
    try:
        engine = WhisperXEngine(args.model, args.compute_type, "en", args.threads, args.batch_size)
    except ModelMissingError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    log(f"[asr] WhisperX {args.model} ({args.compute_type}, cpu, {args.threads} threads) and the "
        f"English aligner loaded in {engine.load_s:.1f} s")
    clock = ClockTracker(args.serial, args.clock_refresh_min * 60, log)
    watchdog = Watchdog(args.inbox, outputs, engine, clock=clock, log=log,
                        sessions=set(args.session) if args.session else None)
    log(f"[watchdog] polling {args.inbox} every {args.interval_ms:.0f} ms -> {outputs}")
    already = watchdog.completed_sessions()
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None

    def stop() -> bool:
        if deadline is not None and time.monotonic() > deadline:
            log("[watchdog] --max-minutes reached")
            return True
        return (args.exit_after_sessions is not None
                and len(watchdog.completed_sessions() - already) >= args.exit_after_sessions)

    try:
        watchdog.run(args.interval_ms / 1000, until_idle=args.until_idle, stop=stop)
    except KeyboardInterrupt:
        log("[watchdog] stopped")
    if args.serial:
        clock.measure()  # a closing measurement shows the drift over the run
    summary = {
        "started": started.isoformat(timespec="seconds"),
        "finished": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": engine.info,
        "model_load_s": round(engine.load_s, 2),
        "offline_env": offline_env,
        "network_attempts_blocked": blocked_attempts(),
        "clock_measurements": clock.measurements,
        "chunks_processed": watchdog.processed_count,
        "incomplete_sessions": watchdog.incomplete_sessions(),
    }
    outputs.mkdir(parents=True, exist_ok=True)
    path = outputs / f"run_{started.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log(f"[watchdog] {watchdog.processed_count} chunks processed; network attempts blocked: "
        f"{len(summary['network_attempts_blocked'])}; summary {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
