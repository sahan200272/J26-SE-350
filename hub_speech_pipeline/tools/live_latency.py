#!/usr/bin/env python3
"""Per-stage end-to-end latency of a live session: end of speech -> transcript on the PC.

Joins four records of the same session (stdlib only):

* the phone log (``adb logcat -v time -s flutter``): when each segment was cut
  (``[segment] #N``) and when its files were published to the outbox (``[encode] #N ->``);
* the sidecars in the inbox: ``end_wallclock``, frame size, VAD post-roll, phone encode time;
* the arrival log from ``verify_session.py watch`` (20 ms polls): when each finished file
  appeared in the inbox;
* the hub's chunk transcripts: ready / processing-start / written times (PC clock).

Phone times are converted to PC time with the measured phone - PC clock offset
(``pc = phone - offset``). Stages per chunk (ms)::

    vad_wait   = segment cut (phone log)            - end of speech (phone)
    encode     = files published (phone log)        - segment cut      (queue + Opus encode + SHA + writes)
    delivery   = later of .opus/.json in the inbox  - files published  (Syncthing, phone -> PC)
    pc_detect  = chunk ready (hub)                  - arrival          (200 ms polls + stability + SHA)
    pc_queue   = processing started (hub)           - chunk ready
    asr        = transcript written (hub)           - processing started (decode + ASR + alignment)
    total      = transcript written                 - end of speech    (= sum of the stages)

End of speech = ``end_wallclock`` minus the VAD post-roll when the segment was closed by the
hangover (the segmenter appends ``post_roll_frames`` of non-speech after the last speech frame).
For a forced split or a segment flushed by Stop it is ``end_wallclock`` itself.

    python hub_speech_pipeline/tools/live_latency.py --session-dir <inbox>/<sid> \\
        --hub-dir <outputs>/whisperx-small-int8/<sid> --phone-log phone_logcat.txt \\
        --arrivals arrivals.jsonl --hub-run <outputs>/whisperx-small-int8/run_*.json [--json out.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_session import combine_offsets, load_arrivals, wallclock_ns  # noqa: E402

LOG_TIME = re.compile(r"^(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\.(\d{3})")
STAGES = ["vad_wait", "encode", "delivery", "pc_detect", "pc_queue", "asr"]


def phone_log_times(text: str, session_id: str, year: int, tz: dt.tzinfo) -> dict[int, dict[str, int]]:
    """seq -> {"cut": ns, "published": ns} for ``session_id`` (phone clock)."""
    out: dict[int, dict[str, int]] = {}
    current = None
    for line in text.splitlines():
        m = LOG_TIME.match(line)
        if not m:
            continue
        mo, d, h, mi, s, ms = map(int, m.groups())
        t = dt.datetime(year, mo, d, h, mi, s, ms * 1000, tzinfo=tz)
        ns = (t - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)) // dt.timedelta(microseconds=1) * 1000
        if sm := re.search(r"\[session\] (\S+) started", line):
            current = sm.group(1)  # segment/encode lines carry no session ID
        if current != session_id:
            continue
        if sm := re.search(r"\[segment\] #(\d+) ", line):
            out.setdefault(int(sm.group(1)), {})["cut"] = ns
        elif sm := re.search(r"\[encode\] #(\d+) →", line):
            out.setdefault(int(sm.group(1)), {})["published"] = ns
    return out


def end_of_speech_ns(sidecar: dict, session_end_ms: float | None) -> tuple[int, str]:
    """(end of speech on the phone clock, how the segment ended)."""
    end_ns = wallclock_ns(sidecar["end_wallclock"])
    if sidecar.get("forced_split"):
        return end_ns, "forced split (speech continued)"
    frame_ms = sidecar["samples"] / sidecar["frames"] / sidecar["sample_rate"] * 1000
    post_roll_ms = sidecar["segmenter"]["config"]["post_roll_frames"] * frame_ms
    if session_end_ms is not None and session_end_ms - sidecar["end_ms"] < post_roll_ms:
        return end_ns, "flushed by Stop"
    return end_ns - round(post_roll_ms * 1e6), f"hangover (end minus {post_roll_ms:.0f} ms post-roll)"


def stages(sidecar: dict, phone: dict[str, int], arrival_ns: int, hub: dict, offset_ms: float,
           session_end_ms: float | None) -> dict:
    off = offset_ms * 1e6
    eos, how = end_of_speech_ns(sidecar, session_end_ms)
    ready = wallclock_ns(hub["arrival"]["ready_pc"])
    start = wallclock_ns(hub["arrival"]["processing_started_pc"])
    written = wallclock_ns(hub["latency"]["transcript_written_pc"])
    ms = lambda a, b: round((a - b) / 1e6, 1)  # noqa: E731
    row = {
        "seq": sidecar["seq"],
        "audio_s": round(sidecar["samples"] / sidecar["sample_rate"], 3),
        "segment_end": how,
        "vad_wait": ms(phone["cut"], eos),
        "encode": ms(phone["published"], phone["cut"]),
        "phone_encode_ms": sidecar["processing"]["encode_ms"],
        "delivery": ms(arrival_ns, phone["published"] - off),
        "pc_detect": ms(ready, arrival_ns),
        "pc_queue": ms(start, ready),
        "asr": ms(written, start),
        "total": ms(written, eos - off),
        "from_chunk_end": ms(written, wallclock_ns(sidecar["end_wallclock"]) - off),
    }
    row["stage_sum"] = round(sum(row[s] for s in STAGES), 1)
    return row


def analyse(session_dir: Path, hub_dir: Path, phone_log: str, arrivals: dict, clock: dict) -> dict:
    sid = session_dir.name
    manifest = json.loads((session_dir / f"{sid}_manifest.json").read_text(encoding="utf-8"))
    sidecars = {}
    for p in sorted(session_dir.glob(f"{sid}_[0-9][0-9][0-9][0-9][0-9].json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        sidecars[s["seq"]] = s
    first = next(iter(sidecars.values()))
    end = dt.datetime.fromisoformat(first["end_wallclock"])
    phone = phone_log_times(phone_log, sid, end.year, end.tzinfo)
    rows = []
    for seq, sidecar in sorted(sidecars.items()):
        hub = json.loads((hub_dir / f"{sid}_{seq:05d}.transcript.json").read_text(encoding="utf-8"))
        arrival = max(arrivals[f"{sid}/{sidecar['audio_file']}"][0],
                      arrivals[f"{sid}/{sid}_{seq:05d}.json"][0])
        rows.append(stages(sidecar, phone[seq], arrival, hub, clock["offset_ms"], manifest.get("session_end_ms")))
    summary = {k: {"median": round(statistics.median(r[k] for r in rows), 1), "max": max(r[k] for r in rows)}
               for k in STAGES + ["total", "from_chunk_end"]}
    arrival_unc = max(half for t, half in arrivals.values()) / 1e6 if arrivals else None
    return {"session_id": sid, "clock": clock, "rows": rows, "summary": summary,
            "uncertainty_ms": {"total": round(clock["uncertainty_ms"] + 1.0, 1),
                               "delivery": round(clock["uncertainty_ms"] + (arrival_unc or 0) + 1.0, 1),
                               "pc_detect": round((arrival_unc or 0) + 0.5, 1),
                               "note": "total: clock offset + 2 x 0.5 ms timestamp precision; stage boundaries on "
                                       "the PC side also carry the arrival-poll uncertainty"}}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--session-dir", type=Path, required=True)
    p.add_argument("--hub-dir", type=Path, required=True)
    p.add_argument("--phone-log", type=Path, required=True)
    p.add_argument("--arrivals", type=Path, required=True)
    p.add_argument("--hub-run", type=Path, help="hub run summary JSON (its clock measurements are used)")
    p.add_argument("--clock", type=Path, action="append", default=[], help="clock JSON(s) from verify_session clock")
    p.add_argument("--json", type=Path)
    args = p.parse_args(argv)
    measurements = [json.loads(c.read_text(encoding="utf-8")) for c in args.clock]
    if args.hub_run:
        measurements += json.loads(args.hub_run.read_text(encoding="utf-8"))["clock_measurements"]
    if not measurements:
        p.error("need --hub-run or --clock for the phone/PC offset")
    result = analyse(args.session_dir, args.hub_dir, args.phone_log.read_text(encoding="utf-8", errors="replace"),
                     load_arrivals(args.arrivals), combine_offsets(measurements))
    cols = ["seq", "audio_s"] + STAGES + ["total", "from_chunk_end"]
    print(" ".join(f"{c:>10}" for c in cols))
    for r in result["rows"]:
        print(" ".join(f"{r[c]:>10}" for c in cols))
    for k, v in result["summary"].items():
        print(f"{k:>15}: median {v['median']:8.1f} ms   max {v['max']:8.1f} ms")
    c = result["clock"]
    print(f"clock offset {c['offset_ms']:.2f} ms +/- {c['uncertainty_ms']:.2f} ms (drift {c['drift_ms']:.2f} ms); "
          f"total latency uncertainty +/- {result['uncertainty_ms']['total']} ms")
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
