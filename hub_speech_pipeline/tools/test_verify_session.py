"""Unit tests for verify_session.py (stdlib unittest).

Run in the c1-speech env from the repository root:
    python -m unittest discover -s hub_speech_pipeline/tools -v
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_session as vs  # noqa: E402

SID = "20261018T100000_a1b2"


def ogg_page(packets: list[bytes], granule: int, seq: int, flags: int = 0) -> bytes:
    table = bytearray()
    for p in packets:
        n = len(p)
        while n >= 255:
            table.append(255)
            n -= 255
        table.append(n)
    header = b"OggS" + bytes([0, flags]) + struct.pack("<qIII", granule, 1, seq, 0) + bytes([len(table)])
    return header + bytes(table) + b"".join(packets)


def ogg_opus(channels: int = 1, pre_skip: int = 312, rate: int = 16000, frames: int = 50) -> bytes:
    """A structurally valid Ogg Opus file (dummy audio packets, CRC not set)."""
    head = b"OpusHead" + bytes([1, channels]) + struct.pack("<HIhB", pre_skip, rate, 0, 0)
    tags = b"OpusTags" + struct.pack("<I", 4) + b"test" + struct.pack("<I", 0)
    pages = [ogg_page([head], 0, 0, 2), ogg_page([tags], 0, 1)]
    for i in range(frames):
        pages.append(ogg_page([bytes([0xFC]) + bytes(40)], pre_skip + 960 * (i + 1), i + 2, 4 if i == frames - 1 else 0))
    return b"".join(pages)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_session(root: Path, sample_counts=(16000, 32000, 8000), audio=None) -> Path:
    """Writes a session folder like the app's outbox: chunks, sidecars, manifest."""
    d = root / SID
    d.mkdir(parents=True)
    chunks = []
    for seq, samples in enumerate(sample_counts):
        base = f"{SID}_{seq:05d}"
        data = audio(seq, samples) if audio else ogg_opus(frames=samples // 320)
        (d / f"{base}.opus").write_bytes(data)
        sidecar = {
            "schema_version": "c1-chunk/0.1", "session_id": SID, "seq": seq,
            "audio_file": f"{base}.opus", "codec": "opus", "sample_rate": 16000, "channels": 1,
            "start_wallclock": "2026-10-18T10:00:00.000+05:30",
            "end_wallclock": f"2026-10-18T10:00:{10 + seq * 10:02d}.000+05:30",
            "samples": samples, "frames": samples // 512, "sha256": sha(data),
            "processing": {"queue_wait_ms": 1.0, "encode_ms": 500.0, "queue_length_at_enqueue": 1},
        }
        side_bytes = (json.dumps(sidecar, indent=2) + "\n").encode()
        (d / f"{base}.json").write_bytes(side_bytes)
        chunks.append({"seq": seq, "audio_file": f"{base}.opus", "sidecar_file": f"{base}.json",
                       "sha256": sha(data), "sidecar_sha256": sha(side_bytes), "opus_bytes": len(data)})
    manifest = {
        "schema_version": "c1-manifest/0.1", "session_id": SID, "chunk_count": len(chunks),
        "seqs": list(range(len(chunks))), "chunks": chunks, "failed_chunks": [],
        "recorded_ms": 30000.0, "pause_intervals": [],
        "frame_accounting": {"balanced": True, "segments_emitted": len(chunks),
                             "frames_in_segments": sum(s // 512 for s in sample_counts),
                             "samples_in_segments": sum(sample_counts)},
    }
    (d / f"{SID}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return d


def fake_probe(duration_offset_s: float = 0.0, codec: str = "opus", channels: int = 1):
    """ffprobe stand-in: duration = sidecar samples / 16 kHz + offset."""

    def probe(path: Path) -> dict:
        samples = json.loads(path.with_suffix(".json").read_text())["samples"]
        return {"format": "ogg", "codec": codec, "channels": channels, "sample_rate": 48000,
                "duration_s": samples / 16000 + duration_offset_s}

    return probe


def failed(report: vs.Report) -> list[str]:
    return [c.name for c in report.checks if not c.ok]


class SessionChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_session_passes(self):
        d = make_session(self.root)
        report, manifest, sidecars = vs.verify_session(d, fake_probe())
        self.assertEqual(failed(report), [])
        self.assertTrue(report.ok)
        self.assertEqual(sorted(sidecars), [0, 1, 2])
        self.assertEqual(report.summary["chunk_count"], 3)
        self.assertEqual(report.summary["speech_samples"], 56000)

    def test_missing_audio_file_fails(self):
        d = make_session(self.root)
        (d / f"{SID}_00001.opus").unlink()
        report, _, _ = vs.verify_session(d, fake_probe())
        self.assertIn("#1 files present", failed(report))
        self.assertIn("all listed files present", failed(report))
        self.assertFalse(report.ok)

    def test_missing_manifest_fails(self):
        d = make_session(self.root)
        (d / f"{SID}_manifest.json").unlink()
        report, manifest, _ = vs.verify_session(d, fake_probe())
        self.assertEqual(failed(report), ["exactly one manifest"])
        self.assertEqual(manifest, {})

    def test_seq_gap_fails(self):
        d = make_session(self.root)
        path = d / f"{SID}_manifest.json"
        m = json.loads(path.read_text())
        m["seqs"] = [0, 2]
        m["chunks"] = [c for c in m["chunks"] if c["seq"] != 1]
        m["chunk_count"] = 2
        path.write_text(json.dumps(m))
        report, _, _ = vs.verify_session(d, fake_probe())
        self.assertIn("seqs are 0..n-1 without gaps", failed(report))
        self.assertIn("no unlisted chunk files", failed(report))  # 00001 files left over

    def test_modified_audio_fails_sha256(self):
        d = make_session(self.root)
        p = d / f"{SID}_00002.opus"
        data = bytearray(p.read_bytes())
        data[-1] ^= 0xFF
        p.write_bytes(bytes(data))
        report, _, _ = vs.verify_session(d, fake_probe())
        self.assertIn("#2 SHA-256 of .opus = manifest", failed(report))
        self.assertIn("#2 SHA-256 of .opus = sidecar", failed(report))

    def test_modified_sidecar_fails_sha256(self):
        d = make_session(self.root)
        p = d / f"{SID}_00000.json"
        p.write_text(p.read_text().replace('"codec": "opus"', '"codec": "opus "'))
        report, _, _ = vs.verify_session(d, fake_probe())
        self.assertEqual(failed(report), ["#0 SHA-256 of .json = manifest"])

    def test_temporary_and_unlisted_files_fail(self):
        d = make_session(self.root)
        (d / f"~syncthing~{SID}_00003.opus.tmp").write_bytes(b"partial")
        (d / f"{SID}_00007.opus").write_bytes(b"stray")
        report, _, _ = vs.verify_session(d, fake_probe())
        self.assertIn("no Syncthing temporary files (transfer complete)", failed(report))
        self.assertIn("no unlisted chunk files", failed(report))

    def test_failed_chunks_and_accounting_mismatch_fail(self):
        d = make_session(self.root)
        path = d / f"{SID}_manifest.json"
        m = json.loads(path.read_text())
        m["failed_chunks"] = [{"seq": 3, "error": "encode failed"}]
        m["frame_accounting"]["samples_in_segments"] += 1
        path.write_text(json.dumps(m))
        report, _, _ = vs.verify_session(d, fake_probe())
        self.assertIn("no failed chunks", failed(report))
        self.assertIn("samples_in_segments = sum of sidecar samples", failed(report))
        self.assertIn("segments_emitted = chunks + failed", failed(report))

    def test_wrong_rate_or_channels_fail(self):
        d = make_session(self.root, audio=lambda seq, n: ogg_opus(
            channels=2 if seq == 0 else 1, rate=48000 if seq == 1 else 16000, frames=n // 320))
        report, _, _ = vs.verify_session(d, fake_probe())
        self.assertIn("#0 OpusHead: 16 kHz input, mono", failed(report))
        self.assertIn("#1 OpusHead: 16 kHz input, mono", failed(report))
        self.assertNotIn("#2 OpusHead: 16 kHz input, mono", failed(report))
        report, _, _ = vs.verify_session(make_session(self.root / "b"), fake_probe(channels=2))
        self.assertIn("#0 ffprobe: Ogg Opus, mono", failed(report))

    def test_duration_tolerance_is_pre_skip_plus_one_frame(self):
        d = make_session(self.root)  # pre-skip 312 = 6.5 ms; tolerance 6.5 + 20 + 1 ms
        for offset, ok in [(0.0, True), (-0.020, True), (0.027, True), (-0.028, False), (0.05, False)]:
            report, _, _ = vs.verify_session(d, fake_probe(offset))
            duration_failures = [n for n in failed(report) if "duration" in n]
            self.assertEqual(not duration_failures, ok, f"offset {offset}: {duration_failures}")


class Primitives(unittest.TestCase):
    def test_read_opus_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp, "x.opus")
            p.write_bytes(ogg_opus(channels=1, pre_skip=104, rate=16000, frames=10))
            head = vs.read_opus_head(p)
        self.assertEqual((head.channels, head.pre_skip, head.input_sample_rate), (1, 104, 16000))
        self.assertEqual(head.last_granule, 104 + 9600)
        self.assertEqual(head.pages, 12)
        self.assertAlmostEqual(head.duration_s, 0.2)

    def test_read_opus_head_rejects_non_opus(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp, "x.opus")
            p.write_bytes(b"RIFF....WAVE")
            with self.assertRaises(ValueError):
                vs.read_opus_head(p)

    def test_wallclock_ns(self):
        self.assertEqual(vs.wallclock_ns("1970-01-01T05:30:00.001+05:30"), 1_000_000)
        self.assertEqual(vs.wallclock_ns("2026-10-18T01:32:49.990+05:30"),
                         vs.wallclock_ns("2026-10-17T20:02:49.990+00:00"))
        with self.assertRaises(ValueError):
            vs.wallclock_ns("2026-10-18T01:32:49.990")

    def test_offset_uses_tightest_bracket(self):
        ms = 1_000_000
        samples = [  # (PC before, phone, PC after) in ns
            vs.ClockSample(1000 * ms, 1560 * ms, 1100 * ms),  # rtt 100 ms, offset 510 ms
            vs.ClockSample(2000 * ms, 2505 * ms, 2010 * ms),  # rtt 10 ms, offset 500 ms
            vs.ClockSample(3000 * ms, 3520 * ms, 3060 * ms),  # rtt 60 ms, offset 490 ms
        ]
        r = vs.estimate_offset(samples)
        self.assertAlmostEqual(r["offset_ms"], 500.0)
        self.assertAlmostEqual(r["uncertainty_ms"], 5.0)
        self.assertAlmostEqual(r["best_rtt_ms"], 10.0)
        self.assertAlmostEqual(r["median_rtt_ms"], 60.0)
        self.assertAlmostEqual(r["offset_spread_ms"], 20.0)
        self.assertEqual(r["samples"], 3)

    def test_combined_offset_adds_half_the_drift(self):
        r = vs.combine_offsets([{"offset_ms": 100.0, "uncertainty_ms": 4.0},
                                {"offset_ms": 106.0, "uncertainty_ms": 3.0}])
        self.assertAlmostEqual(r["offset_ms"], 103.0)
        self.assertAlmostEqual(r["drift_ms"], 6.0)
        self.assertAlmostEqual(r["uncertainty_ms"], 7.0)

    def test_poll_once_skips_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp)
            (inbox / SID).mkdir()
            (inbox / SID / "a.opus").write_bytes(b"x")
            (inbox / SID / "~syncthing~b.opus.tmp").write_bytes(b"x")
            (inbox / SID / ".syncthing.c.json.tmp").write_bytes(b"x")
            seen: dict[str, int] = {}
            self.assertEqual(vs.poll_once(inbox, seen), [f"{SID}/a.opus"])
            seen[f"{SID}/a.opus"] = 1
            self.assertEqual(vs.poll_once(inbox, seen), [])

    def test_load_arrivals_takes_poll_midpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "arrivals.jsonl")
            log.write_text("\n".join([
                json.dumps({"event": "start", "pc_ns": 0}),
                json.dumps({"path": "s/a.opus", "seen_ns": 1_020_000_000, "previous_poll_ns": 1_000_000_000}),
                json.dumps({"path": "s/a.opus", "seen_ns": 9_000_000_000, "previous_poll_ns": 8_000_000_000}),
            ]))
            self.assertEqual(vs.load_arrivals(log), {"s/a.opus": (1_010_000_000, 10_000_000)})


class Latency(unittest.TestCase):
    def test_latency_is_later_arrival_minus_end_in_pc_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_session(Path(tmp), sample_counts=(16000, 16000))
            report, manifest, sidecars = vs.verify_session(d, fake_probe())
            self.assertTrue(report.ok)
            end0 = vs.wallclock_ns(sidecars[0]["end_wallclock"])
            end1 = vs.wallclock_ns(sidecars[1]["end_wallclock"])
            offset_ms = 250.0  # phone clock 250 ms ahead of the PC
            ms = 1_000_000
            arrivals = {
                # chunk 0: .json after .opus; chunk 1: .opus after .json
                f"{SID}/{SID}_00000.opus": (end0 - 250 * ms + 900 * ms, 10 * ms),
                f"{SID}/{SID}_00000.json": (end0 - 250 * ms + 1000 * ms, 10 * ms),
                f"{SID}/{SID}_00001.opus": (end1 - 250 * ms + 1600 * ms, 10 * ms),
                f"{SID}/{SID}_00001.json": (end1 - 250 * ms + 1500 * ms, 10 * ms),
            }
            lat = vs.chunk_latencies(d, manifest, sidecars, {"offset_ms": offset_ms, "uncertainty_ms": 4.0}, arrivals)
        self.assertEqual([r["latency_ms"] for r in lat["chunks"]], [1000.0, 1600.0])
        self.assertEqual(lat["median_ms"], 1300.0)
        self.assertEqual(lat["max_ms"], 1600.0)
        self.assertEqual(lat["uncertainty_ms"], 14.5)  # 4 clock + 10 arrival + 0.5 timestamps
        self.assertEqual([r["opus_after_json_ms"] for r in lat["chunks"]], [-100.0, 100.0])

    def test_missing_arrival_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_session(Path(tmp), sample_counts=(16000,))
            _, manifest, sidecars = vs.verify_session(d, fake_probe())
            with self.assertRaises(KeyError):
                vs.chunk_latencies(d, manifest, sidecars, {"offset_ms": 0, "uncertainty_ms": 1}, {})

    @unittest.skipUnless(sys.platform == "win32", "creation time fallback is used on Windows")
    def test_creation_time_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_session(Path(tmp), sample_counts=(16000,))
            _, manifest, sidecars = vs.verify_session(d, fake_probe())
            lat = vs.chunk_latencies(d, manifest, sidecars, {"offset_ms": 0, "uncertainty_ms": 1}, None)
        self.assertEqual(lat["count"], 1)
        self.assertIn("creation time", lat["arrival_source"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg and ffprobe")
class WithFfmpeg(unittest.TestCase):
    """End to end with real Ogg Opus files (libopus, 16 kHz mono) and real ffprobe."""

    @staticmethod
    def encode(seq: int, samples: int) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "x.opus")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi",
                 "-i", f"sine=frequency={300 + 100 * seq}:sample_rate=16000:duration={samples / 16000}",
                 "-ac", "1", "-c:a", "libopus", "-b:a", "32k", str(out)],
                check=True,
            )
            return out.read_bytes()

    def test_real_files_pass_and_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_session(Path(tmp), sample_counts=(16000, 24000), audio=self.encode)
            report, _, _ = vs.verify_session(d)
            self.assertEqual(failed(report), [])
            for row in report.chunks:
                self.assertLessEqual(abs(row["duration_difference_ms"]), 7.0)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(vs.main(["verify", str(d), "--json", str(Path(tmp, "r.json"))]), 0)
            self.assertIn("ALL CHECKS PASSED", out.getvalue())
            self.assertTrue(json.loads(Path(tmp, "r.json").read_text())["all_checks_passed"])
            (d / f"{SID}_00001.opus").unlink()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(vs.main(["verify", str(d)]), 1)


if __name__ == "__main__":
    unittest.main()
