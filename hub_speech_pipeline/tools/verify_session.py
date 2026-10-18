#!/usr/bin/env python3
"""Verify a Component 1 recording session delivered to the PC by Syncthing (A5).

Python standard library plus ffprobe (FFmpeg) only.

Commands
--------
verify SESSION_DIR [--arrivals FILE] [--clock FILE ...] [--json OUT]
    Checks one delivered session folder (``<inbox>/<session_id>/``):

    * manifest completeness: exactly one ``<session_id>_manifest.json``
      (schema ``c1-manifest/0.1``), seqs 0..n-1 with no gaps, every listed
      ``.opus`` and ``.json`` present, no unlisted chunk files, no Syncthing
      temporary files, no failed chunks, balanced frame accounting whose
      totals equal the sums over the sidecars;
    * SHA-256 of every ``.opus`` (against the manifest and its sidecar) and
      of every sidecar (against the manifest);
    * audio: every ``.opus`` is Ogg Opus with OpusHead input rate 16000 Hz
      and 1 channel, ffprobe agrees (codec opus, 1 channel), and its duration
      matches the sidecar's sample count within the Opus pre-skip plus one
      20 ms frame (the encoder pads the last frame);
    * transfer latency per chunk, when ``--clock`` is given:
      arrival on the PC (the later of its ``.opus`` and ``.json``) minus the
      chunk's ``end_wallclock``, after converting phone time to PC time with
      the measured clock offset. Median and max are reported with their
      uncertainty.

clock --serial SERIAL [--samples N] [--out FILE]
    Measures the phone-minus-PC wall-clock offset over adb: repeatedly runs
    ``date +%s%N`` in one ``adb shell`` and brackets each answer between two
    PC timestamps. The phone read its clock somewhere inside that bracket, so
    the offset is known to within half the shortest round trip (reported as
    the uncertainty). Run it before and after a recording and pass both files
    to ``verify``; their difference (drift) is added to the uncertainty.

watch INBOX_DIR --out FILE [--interval-ms MS] [--duration-s S]
    Logs when each file appears in the inbox (Syncthing renames a finished
    temporary file into place, so this is the arrival of the complete file).
    Each record holds the poll that first saw the file and the poll before
    it; the arrival is taken as their midpoint, uncertain by half the gap.
    Without this log, ``verify`` falls back to each file's creation time,
    i.e. when Syncthing created its temporary file (start of the download).

Exit status: 0 if every check passed, 1 if any failed, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterable

CHUNK_SCHEMA = "c1-chunk/0.1"
MANIFEST_SCHEMA = "c1-manifest/0.1"
SAMPLE_RATE = 16000
OPUS_GRANULE_RATE = 48000  # Ogg Opus granule positions and pre-skip use 48 kHz
OPUS_FRAME_S = 0.020  # the last frame is padded to a full 20 ms frame
TOLERANCE_EXTRA_S = 0.001  # rounding of container timestamps
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
# Syncthing's temporary files: ".syncthing.<name>.tmp" (Unix), "~syncthing~<name>.tmp" (Windows).
TEMP_FILE = re.compile(r"^(\.syncthing\.|~syncthing~).*\.tmp$")


# --- results -------------------------------------------------------------------------------


@dataclasses.dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclasses.dataclass
class Report:
    session_dir: str
    checks: list[Check] = dataclasses.field(default_factory=list)
    chunks: list[dict] = dataclasses.field(default_factory=list)
    summary: dict = dataclasses.field(default_factory=dict)
    latency: dict | None = None

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(Check(name, bool(ok), detail))
        return bool(ok)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def to_json(self) -> dict:
        return {
            "session_dir": self.session_dir,
            "all_checks_passed": self.ok,
            "checks": [dataclasses.asdict(c) for c in self.checks],
            "summary": self.summary,
            "chunks": self.chunks,
            "latency": self.latency,
        }


# --- primitives ----------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def wallclock_ns(text: str) -> int:
    """ISO 8601 with a UTC offset (e.g. 2026-10-18T01:32:49.990+05:30) -> Unix ns."""
    value = dt.datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise ValueError(f"wall-clock time without UTC offset: {text!r}")
    return (value - EPOCH) // dt.timedelta(microseconds=1) * 1000


def ns_to_iso(ns: int) -> str:
    return (EPOCH + dt.timedelta(microseconds=ns // 1000)).astimezone().isoformat(
        timespec="milliseconds"
    )


@dataclasses.dataclass
class OpusHead:
    channels: int
    pre_skip: int  # in 48 kHz samples
    input_sample_rate: int
    last_granule: int  # granule position of the last page (48 kHz samples)
    pages: int

    @property
    def duration_s(self) -> float:
        """Playable duration from the granule positions (after pre-skip)."""
        return (self.last_granule - self.pre_skip) / OPUS_GRANULE_RATE


def read_opus_head(path: Path) -> OpusHead:
    """Reads OpusHead (RFC 7845 §5.1) and the last granule position from an Ogg file."""
    data = path.read_bytes()
    pos = 0
    pages = 0
    head = None
    last_granule = -1
    while pos < len(data):
        if data[pos : pos + 4] != b"OggS" or pos + 27 > len(data):
            raise ValueError(f"{path.name}: not an Ogg page at byte {pos}")
        (granule,) = struct.unpack_from("<q", data, pos + 6)
        segments = data[pos + 26]
        table = data[pos + 27 : pos + 27 + segments]
        body = pos + 27 + segments
        if pages == 0:
            # The first page holds only OpusHead (19+ bytes).
            first = data[body : body + sum(table)]
            if first[:8] != b"OpusHead" or len(first) < 19:
                raise ValueError(f"{path.name}: first packet is not OpusHead")
            pre_skip, rate = struct.unpack_from("<HI", first, 10)
            head = (first[9], pre_skip, rate)
        if granule >= 0:
            last_granule = granule
        pos = body + sum(table)
        pages += 1
    if head is None:
        raise ValueError(f"{path.name}: empty file")
    return OpusHead(head[0], head[1], head[2], last_granule, pages)


def ffprobe(path: Path) -> dict:
    """codec, channels, sample rate and duration of the first audio stream."""
    exe = shutil.which("ffprobe")
    if exe is None:
        raise RuntimeError("ffprobe not found on PATH")
    out = subprocess.run(
        [
            exe, "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,channels,sample_rate,duration:format=format_name,duration",
            "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True,
    ).stdout
    info = json.loads(out)
    stream = (info.get("streams") or [{}])[0]
    fmt = info.get("format", {})
    duration = stream.get("duration") or fmt.get("duration")
    return {
        "format": fmt.get("format_name"),
        "codec": stream.get("codec_name"),
        "channels": int(stream["channels"]) if "channels" in stream else None,
        "sample_rate": int(stream["sample_rate"]) if "sample_rate" in stream else None,
        "duration_s": float(duration) if duration is not None else None,
    }


# --- session checks ------------------------------------------------------------------------


def verify_session(session_dir: Path, probe: Callable[[Path], dict] = ffprobe) -> tuple[Report, dict, dict]:
    """Returns (report, manifest, sidecars by seq). Never raises for content problems."""
    report = Report(str(session_dir))
    manifest: dict = {}
    sidecars: dict[int, dict] = {}
    if not report.add("session folder exists", session_dir.is_dir(), str(session_dir)):
        return report, manifest, sidecars

    files = sorted(p for p in session_dir.iterdir() if p.is_file())
    temps = [p.name for p in files if TEMP_FILE.match(p.name)]
    report.add("no Syncthing temporary files (transfer complete)", not temps, ", ".join(temps))

    manifests = [p for p in files if p.name.endswith("_manifest.json")]
    if not report.add("exactly one manifest", len(manifests) == 1, ", ".join(p.name for p in manifests)):
        return report, manifest, sidecars
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    session_id = manifest.get("session_id")
    report.add("manifest schema", manifest.get("schema_version") == MANIFEST_SCHEMA,
               str(manifest.get("schema_version")))
    report.add("manifest file name and folder match session_id",
               manifests[0].name == f"{session_id}_manifest.json" and session_dir.name == session_id,
               f"session_id={session_id}, folder={session_dir.name}")

    chunks = sorted(manifest.get("chunks", []), key=lambda c: c["seq"])
    count = manifest.get("chunk_count")
    seqs = manifest.get("seqs", [])
    report.add("seqs are 0..n-1 without gaps", seqs == list(range(len(seqs))), str(seqs))
    report.add("chunk_count = len(seqs) = len(chunks)",
               count == len(seqs) == len(chunks) and [c["seq"] for c in chunks] == seqs,
               f"chunk_count={count}, seqs={len(seqs)}, chunks={len(chunks)}")
    failed = manifest.get("failed_chunks", [])
    report.add("no failed chunks", not failed, json.dumps(failed))

    listed = {manifests[0].name}
    totals = {"frames": 0, "samples": 0, "opus_bytes": 0}
    missing: list[str] = []
    for chunk in chunks:
        seq = chunk["seq"]
        audio = session_dir / chunk["audio_file"]
        side = session_dir / chunk["sidecar_file"]
        listed.update({audio.name, side.name})
        expected_base = f"{session_id}_{seq:05d}"
        report.add(f"#{seq} file names", audio.name == f"{expected_base}.opus" and side.name == f"{expected_base}.json",
                   f"{audio.name}, {side.name}")
        if not audio.is_file() or not side.is_file():
            missing += [p.name for p in (audio, side) if not p.is_file()]
            report.add(f"#{seq} files present", False, "missing: " + ", ".join(p.name for p in (audio, side) if not p.is_file()))
            continue
        sidecar = json.loads(side.read_text(encoding="utf-8"))
        sidecars[seq] = sidecar
        audio_sha = sha256_file(audio)
        report.add(f"#{seq} SHA-256 of .opus = manifest", audio_sha == chunk.get("sha256"), audio_sha)
        report.add(f"#{seq} SHA-256 of .opus = sidecar", audio_sha == sidecar.get("sha256"))
        report.add(f"#{seq} SHA-256 of .json = manifest", sha256_file(side) == chunk.get("sidecar_sha256"))
        report.add(f"#{seq} sidecar identifies its chunk",
                   sidecar.get("schema_version") == CHUNK_SCHEMA and sidecar.get("session_id") == session_id
                   and sidecar.get("seq") == seq and sidecar.get("audio_file") == audio.name,
                   f"schema={sidecar.get('schema_version')}")
        size = audio.stat().st_size
        report.add(f"#{seq} size = manifest opus_bytes", size == chunk.get("opus_bytes"), f"{size} B")

        row = _check_audio(report, seq, audio, sidecar, probe)
        row.update({"seq": seq, "opus_bytes": size, "samples": sidecar.get("samples"),
                    "end_wallclock": sidecar.get("end_wallclock")})
        report.chunks.append(row)
        totals["frames"] += sidecar.get("frames", 0)
        totals["samples"] += sidecar.get("samples", 0)
        totals["opus_bytes"] += size

    report.add("all listed files present", not missing, ", ".join(missing))
    unlisted = [p.name for p in files if p.suffix in (".opus", ".json") and p.name not in listed]
    report.add("no unlisted chunk files", not unlisted, ", ".join(unlisted))

    acc = manifest.get("frame_accounting", {})
    report.add("frame accounting balanced", acc.get("balanced") is True)
    report.add("frames_in_segments = sum of sidecar frames",
               acc.get("frames_in_segments") == totals["frames"],
               f"{acc.get('frames_in_segments')} vs {totals['frames']}")
    report.add("samples_in_segments = sum of sidecar samples",
               acc.get("samples_in_segments") == totals["samples"],
               f"{acc.get('samples_in_segments')} vs {totals['samples']}")
    report.add("segments_emitted = chunks + failed",
               acc.get("segments_emitted") == len(chunks) + len(failed),
               f"{acc.get('segments_emitted')} vs {len(chunks)} + {len(failed)}")

    pcm_bytes = totals["samples"] * 2
    report.summary = {
        "session_id": session_id,
        "chunk_count": len(chunks),
        "recorded_ms": manifest.get("recorded_ms"),
        "pause_intervals": manifest.get("pause_intervals"),
        "speech_samples": totals["samples"],
        "speech_seconds": totals["samples"] / SAMPLE_RATE,
        "opus_bytes": totals["opus_bytes"],
        "pcm_bytes_equivalent": pcm_bytes,
        "compression_ratio": round(pcm_bytes / totals["opus_bytes"], 2) if totals["opus_bytes"] else None,
    }
    return report, manifest, sidecars


def _check_audio(report: Report, seq: int, audio: Path, sidecar: dict, probe: Callable[[Path], dict]) -> dict:
    row: dict = {}
    try:
        head = read_opus_head(audio)
    except ValueError as e:
        report.add(f"#{seq} Ogg Opus header", False, str(e))
        return row
    report.add(f"#{seq} OpusHead: 16 kHz input, mono",
               head.input_sample_rate == SAMPLE_RATE == sidecar.get("sample_rate") and head.channels == 1 == sidecar.get("channels"),
               f"input_sample_rate={head.input_sample_rate}, channels={head.channels}")
    try:
        info = probe(audio)
    except Exception as e:  # ffprobe missing or failing is a failed check, not a crash
        report.add(f"#{seq} ffprobe", False, str(e))
        return row
    report.add(f"#{seq} ffprobe: Ogg Opus, mono",
               info.get("codec") == "opus" and info.get("channels") == 1 and "ogg" in str(info.get("format")),
               f"format={info.get('format')}, codec={info.get('codec')}, channels={info.get('channels')}, "
               f"decode rate={info.get('sample_rate')} Hz")
    expected = sidecar.get("samples", 0) / SAMPLE_RATE
    pre_skip_s = head.pre_skip / OPUS_GRANULE_RATE
    tolerance = pre_skip_s + OPUS_FRAME_S + TOLERANCE_EXTRA_S
    actual = info.get("duration_s")
    ok = actual is not None and abs(actual - expected) <= tolerance
    report.add(f"#{seq} duration matches sample count",
               ok, f"ffprobe {actual} s vs {expected:.4f} s from {sidecar.get('samples')} samples "
                   f"(tolerance +/-{tolerance * 1000:.1f} ms = pre-skip {head.pre_skip} + 20 ms frame + 1 ms)")
    row.update({
        "ffprobe_duration_s": actual,
        "expected_duration_s": round(expected, 4),
        "duration_difference_ms": round((actual - expected) * 1000, 2) if actual is not None else None,
        "granule_duration_s": round(head.duration_s, 4),
        "pre_skip": head.pre_skip,
        "ogg_pages": head.pages,
    })
    return row


# --- clock offset --------------------------------------------------------------------------


@dataclasses.dataclass
class ClockSample:
    pc_before_ns: int
    phone_ns: int
    pc_after_ns: int

    @property
    def rtt_ns(self) -> int:
        return self.pc_after_ns - self.pc_before_ns

    @property
    def offset_ns(self) -> float:
        """phone - PC, assuming the phone read its clock mid-bracket."""
        return self.phone_ns - (self.pc_before_ns + self.pc_after_ns) / 2


def estimate_offset(samples: Iterable[ClockSample]) -> dict:
    """Offset from the tightest bracket; its half round trip bounds the error."""
    samples = list(samples)
    if not samples:
        raise ValueError("no clock samples")
    best = min(samples, key=lambda s: s.rtt_ns)
    return {
        "offset_ms": best.offset_ns / 1e6,
        "uncertainty_ms": best.rtt_ns / 2e6,
        "best_rtt_ms": best.rtt_ns / 1e6,
        "median_rtt_ms": statistics.median(s.rtt_ns for s in samples) / 1e6,
        "samples": len(samples),
        "offset_spread_ms": (max(s.offset_ns for s in samples) - min(s.offset_ns for s in samples)) / 1e6,
        "measured_at": ns_to_iso(best.pc_after_ns),
    }


def combine_offsets(measurements: list[dict]) -> dict:
    """Mean offset; uncertainty = worst single uncertainty + half the drift between them."""
    if not measurements:
        raise ValueError("no clock measurements")
    offsets = [m["offset_ms"] for m in measurements]
    drift = max(offsets) - min(offsets)
    return {
        "offset_ms": statistics.fmean(offsets),
        "uncertainty_ms": max(m["uncertainty_ms"] for m in measurements) + drift / 2,
        "drift_ms": drift,
        "measurements": measurements,
    }


def measure_clock(serial: str, samples: int = 30) -> dict:
    adb = shutil.which("adb")
    if adb is None:
        raise RuntimeError("adb not found on PATH")
    shell = subprocess.Popen(
        [adb, "-s", serial, "shell"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1,
    )
    taken: list[ClockSample] = []
    try:
        for _ in range(samples + 2):
            before = time.time_ns()
            shell.stdin.write("date +%s%N\n")
            shell.stdin.flush()
            line = shell.stdout.readline().strip()
            after = time.time_ns()
            if line.isdigit() and len(line) >= 18:
                taken.append(ClockSample(before, int(line), after))
            time.sleep(0.05)
    finally:
        shell.stdin.close()
        shell.terminate()
    if len(taken) > 2:
        taken = taken[2:]  # the first answers include shell start-up
    result = estimate_offset(taken)
    result["serial"] = serial
    return result


# --- arrivals ------------------------------------------------------------------------------


def poll_once(inbox: Path, seen: dict[str, int]) -> list[str]:
    """New non-temporary files (relative POSIX paths) since the last poll."""
    new = []
    for root, _dirs, names in os.walk(inbox):
        for name in names:
            if TEMP_FILE.match(name):
                continue
            rel = Path(root, name).relative_to(inbox).as_posix()
            if rel not in seen:
                new.append(rel)
    return new


def watch(inbox: Path, out: Path, interval_s: float, duration_s: float | None) -> None:
    seen: dict[str, int] = {}
    start = time.time_ns()
    for rel in poll_once(inbox, seen):
        seen[rel] = start
    previous = time.time_ns()
    with open(out, "a", encoding="utf-8") as log:
        log.write(json.dumps({"event": "start", "inbox": str(inbox), "pc_ns": previous,
                              "preexisting": len(seen), "interval_ms": interval_s * 1000}) + "\n")
        log.flush()
        print(f"watching {inbox} ({len(seen)} files already there); Ctrl+C to stop", flush=True)
        try:
            while duration_s is None or (time.time_ns() - start) / 1e9 < duration_s:
                time.sleep(interval_s)
                new = poll_once(inbox, seen)
                now = time.time_ns()
                for rel in new:
                    seen[rel] = now
                    log.write(json.dumps({"path": rel, "seen_ns": now, "previous_poll_ns": previous}) + "\n")
                    print(f"{ns_to_iso(now)} {rel}", flush=True)
                if new:
                    log.flush()
                previous = now
        except KeyboardInterrupt:
            pass


def load_arrivals(path: Path) -> dict[str, tuple[int, int]]:
    """path -> (arrival estimate ns, half-uncertainty ns) from a watch log."""
    arrivals = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if "path" not in record:
            continue
        lo, hi = record["previous_poll_ns"], record["seen_ns"]
        arrivals.setdefault(record["path"], ((lo + hi) // 2, (hi - lo) // 2))
    return arrivals


def creation_time_ns(path: Path) -> int:
    st = path.stat()
    birth = getattr(st, "st_birthtime_ns", None) or getattr(st, "st_birthtime", None)
    if birth is not None:
        return int(birth if isinstance(birth, int) else birth * 1e9)
    if sys.platform == "win32":
        return st.st_ctime_ns  # creation time on Windows (Python < 3.12)
    raise RuntimeError("file creation time not available on this platform; use a watch log")


def chunk_latencies(session_dir: Path, manifest: dict, sidecars: dict[int, dict],
                    clock: dict, arrivals: dict[str, tuple[int, int]] | None) -> dict:
    """Per-chunk latency = arrival on the PC - end_wallclock (converted to PC time)."""
    offset_ns = clock["offset_ms"] * 1e6
    rows = []
    arrival_unc_ms = 0.0
    session = session_dir.name
    for chunk in sorted(manifest.get("chunks", []), key=lambda c: c["seq"]):
        sidecar = sidecars.get(chunk["seq"])
        if sidecar is None:
            continue
        times = []
        for name in (chunk["audio_file"], chunk["sidecar_file"]):
            if arrivals is not None:
                rel = f"{session}/{name}"
                if rel not in arrivals:
                    raise KeyError(f"{rel} is not in the arrivals log")
                at, half = arrivals[rel]
                arrival_unc_ms = max(arrival_unc_ms, half / 1e6)
            else:
                at = creation_time_ns(session_dir / name)
            times.append(at)
        arrival = max(times)
        end_pc = wallclock_ns(sidecar["end_wallclock"]) - offset_ns
        processing = sidecar.get("processing", {})
        rows.append({
            "seq": chunk["seq"],
            "end_wallclock": sidecar["end_wallclock"],
            "arrival_pc": ns_to_iso(arrival),
            "latency_ms": round((arrival - end_pc) / 1e6, 1),
            "opus_after_json_ms": round((times[0] - times[1]) / 1e6, 1),
            "encode_ms": processing.get("encode_ms"),
            "queue_wait_ms": processing.get("queue_wait_ms"),
        })
    latencies = [r["latency_ms"] for r in rows]
    uncertainty = clock["uncertainty_ms"] + arrival_unc_ms + 0.5  # +0.5 ms: end_wallclock has ms precision
    return {
        "arrival_source": "watch log (file renamed into place)" if arrivals is not None
        else "file creation time (Syncthing's temporary file, i.e. download start)",
        "clock_offset_ms": round(clock["offset_ms"], 2),
        "clock_uncertainty_ms": round(clock["uncertainty_ms"], 2),
        "arrival_uncertainty_ms": round(arrival_unc_ms, 2),
        "uncertainty_ms": round(uncertainty, 1),
        "count": len(rows),
        "median_ms": round(statistics.median(latencies), 1) if rows else None,
        "max_ms": max(latencies) if rows else None,
        "min_ms": min(latencies) if rows else None,
        "chunks": rows,
    }


# --- command line --------------------------------------------------------------------------


def _print_report(report: Report) -> None:
    for c in report.checks:
        # Per-chunk details only when they failed; session-level details always.
        show = c.detail and (not c.ok or not c.name.startswith("#"))
        print(f"[{'PASS' if c.ok else 'FAIL'}] {c.name}" + (f" - {c.detail}" if show else ""))
    s = report.summary
    if s:
        print(f"\nsession {s['session_id']}: {s['chunk_count']} chunks, {s['speech_seconds']:.3f} s speech, "
              f"{s['opus_bytes']} B Opus vs {s['pcm_bytes_equivalent']} B PCM (ratio {s['compression_ratio']})")
    if report.chunks:
        nan = float("nan")
        print("\n seq  samples  expected_s  ffprobe_s  diff_ms  granule_s  pre_skip  bytes")
        for r in report.chunks:
            print(f"{r['seq']:4d}  {r['samples']:7d}  {r.get('expected_duration_s', nan):10.4f}"
                  f"  {r.get('ffprobe_duration_s') or nan:9.4f}  {r.get('duration_difference_ms') or nan:7.2f}"
                  f"  {r.get('granule_duration_s', nan):9.4f}  {r.get('pre_skip', '-'):>8}  {r['opus_bytes']:5d}")
    if report.latency:
        lat = report.latency
        print(f"\nlatency (arrival on PC - end_wallclock), {lat['count']} chunks, arrival from {lat['arrival_source']}:")
        print(" seq  latency_ms  encode_ms  arrival_pc")
        for r in lat["chunks"]:
            print(f"{r['seq']:4d}  {r['latency_ms']:10.1f}  {r['encode_ms'] or 0:9.1f}  {r['arrival_pc']}")
        print(f"median {lat['median_ms']} ms, max {lat['max_ms']} ms, min {lat['min_ms']} ms; "
              f"uncertainty +/-{lat['uncertainty_ms']} ms (clock offset {lat['clock_offset_ms']} ms "
              f"+/-{lat['clock_uncertainty_ms']} ms, arrival +/-{lat['arrival_uncertainty_ms']} ms, timestamps +/-0.5 ms)")
    print("\nALL CHECKS PASSED" if report.ok else "\nSOME CHECKS FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify", help="check a delivered session folder")
    v.add_argument("session_dir", type=Path)
    v.add_argument("--arrivals", type=Path, help="watch log (default: file creation times)")
    v.add_argument("--clock", type=Path, action="append", default=[], help="clock offset file(s) from 'clock'")
    v.add_argument("--json", type=Path, help="write the full report as JSON")
    c = sub.add_parser("clock", help="measure the phone-PC clock offset over adb")
    c.add_argument("--serial", required=True)
    c.add_argument("--samples", type=int, default=30)
    c.add_argument("--out", type=Path)
    w = sub.add_parser("watch", help="log file arrivals in the inbox")
    w.add_argument("inbox", type=Path)
    w.add_argument("--out", type=Path, required=True)
    w.add_argument("--interval-ms", type=float, default=20)
    w.add_argument("--duration-s", type=float)
    args = parser.parse_args(argv)

    if args.command == "clock":
        result = measure_clock(args.serial, args.samples)
        text = json.dumps(result, indent=2)
        print(text)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
        return 0
    if args.command == "watch":
        watch(args.inbox, args.out, args.interval_ms / 1000, args.duration_s)
        return 0

    report, manifest, sidecars = verify_session(args.session_dir)
    if args.clock and manifest:
        clock = combine_offsets([json.loads(p.read_text(encoding="utf-8")) for p in args.clock])
        arrivals = load_arrivals(args.arrivals) if args.arrivals else None
        try:
            report.latency = chunk_latencies(args.session_dir, manifest, sidecars, clock, arrivals)
            report.latency["clock"] = clock
        except (KeyError, RuntimeError) as e:
            report.add("arrival times available", False, str(e))
    _print_report(report)
    if args.json:
        args.json.write_text(json.dumps(report.to_json(), indent=2) + "\n", encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
