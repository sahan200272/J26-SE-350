"""Watchdog rules: readiness, ordering, restart, manifest-before-last-chunk, read-only inbox."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from hub_speech_pipeline.watchdog.watchdog import Watchdog

SID = "20261018T122255_d895"


class FakeEngine:
    info = {"whisper_model": "fake", "compute_type": "int8", "device": "cpu", "language": "en",
            "align_model": "fake-align"}

    def __init__(self):
        self.calls: list[str] = []

    def transcribe(self, audio_path: Path):
        self.calls.append(Path(audio_path).name)
        seq = int(Path(audio_path).stem.rsplit("_", 1)[1])
        segments = [{"text": f" words of chunk {seq}", "start": 0.25, "end": 1.0,
                     "words": [{"word": "words", "start": 0.25, "end": 0.5, "score": 0.9}]}]
        return segments, {"decode_ms": 10.0, "transcribe_ms": 100.0, "align_ms": 20.0, "decoded_duration_s": 1.0}


class Inbox:
    """Builds a session folder the way the phone delivers it."""

    def __init__(self, root: Path, sid: str = SID):
        self.sid = sid
        self.dir = root / sid
        self.dir.mkdir(parents=True)
        self.audio: dict[int, bytes] = {}

    def name(self, seq: int, ext: str) -> Path:
        return self.dir / f"{self.sid}_{seq:05d}.{ext}"

    def sidecar(self, seq: int, audio: bytes | None = None, sha: str | None = None) -> None:
        audio = audio if audio is not None else self.audio.setdefault(seq, f"OggS chunk {seq}".encode() * 10)
        self.audio[seq] = audio
        doc = {"schema_version": "c1-chunk/0.1", "session_id": self.sid, "seq": seq,
               "audio_file": f"{self.sid}_{seq:05d}.opus", "sample_rate": 16000, "channels": 1,
               "samples": 16000, "start_ms": 1000.0 * seq * 2, "end_ms": 1000.0 * seq * 2 + 1000,
               "start_wallclock": "2026-10-18T12:22:56.000+05:30",
               "end_wallclock": "2026-10-18T12:22:57.000+05:30",
               "sha256": sha or hashlib.sha256(audio).hexdigest()}
        self.name(seq, "json").write_text(json.dumps(doc))

    def opus(self, seq: int, data: bytes | None = None) -> None:
        self.name(seq, "opus").write_bytes(data if data is not None else self.audio[seq])

    def chunk(self, seq: int) -> None:
        self.sidecar(seq)
        self.opus(seq)

    def manifest(self, seqs: list[int], failed: list[int] = ()) -> None:
        doc = {"schema_version": "c1-manifest/0.1", "session_id": self.sid,
               "session_start_wallclock": "2026-10-18T12:22:55.034+05:30",
               "session_end_wallclock": "2026-10-18T12:23:27.627+05:30",
               "pause_intervals": [{"start_ms": 30840.2, "end_ms": 32593.5, "reason": "user"}],
               "chunk_count": len(seqs), "seqs": seqs,
               "chunks": [{"seq": s, "audio_file": f"{self.sid}_{s:05d}.opus",
                           "sidecar_file": f"{self.sid}_{s:05d}.json"} for s in seqs],
               "failed_chunks": [{"seq": s, "error": "encode failed"} for s in failed]}
        (self.dir / f"{self.sid}_manifest.json").write_text(json.dumps(doc))


def tree(root: Path) -> dict:
    """Every file under root with size, mtime and content hash."""
    out = {}
    for path in sorted(root.rglob("*")):
        st = path.stat()
        out[path.relative_to(root).as_posix()] = (
            st.st_size, st.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
    return out


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.inbox_root = root / "c1_inbox"
        self.outputs = root / "c1_outputs" / "whisperx-fake-int8"
        self.inbox = Inbox(self.inbox_root)
        self.engine = FakeEngine()
        self.logs: list[str] = []
        self.clock = {"offset_ms": -15.0, "uncertainty_ms": 11.0}
        self.watchdog = self.make()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, engine=None) -> Watchdog:
        return Watchdog(self.inbox_root, self.outputs, engine or self.engine, clock=lambda: self.clock,
                        log=self.logs.append)

    def polls(self, n: int = 2, watchdog: Watchdog | None = None) -> int:
        return sum((watchdog or self.watchdog).poll_once() for _ in range(n))

    def state(self) -> dict:
        return json.loads((self.outputs / "state.json").read_text())["sessions"][SID]

    # --- readiness -----------------------------------------------------------------------

    def test_complete_chunk_needs_two_polls_then_is_processed_once(self):
        self.inbox.chunk(0)
        self.assertEqual(self.watchdog.poll_once(), 0, "first sight: size not yet known to be stable")
        self.assertEqual(self.watchdog.poll_once(), 1)
        self.assertEqual(self.polls(3), 0, "never processed twice")
        self.assertEqual(self.engine.calls, [f"{SID}_00000.opus"])
        out = json.loads((self.outputs / SID / f"{SID}_00000.transcript.json").read_text())
        self.assertEqual(out["audio_sha256"], hashlib.sha256(self.inbox.audio[0]).hexdigest())
        self.assertEqual(out["text"], "words of chunk 0")

    def test_missing_opus_or_json_is_not_ready(self):
        self.inbox.sidecar(0)  # sidecar only (it often arrives first)
        self.assertEqual(self.polls(3), 0)
        self.inbox.opus(0)
        self.assertEqual(self.polls(2), 1)
        # .opus without its sidecar
        self.inbox.audio[1] = b"OggS chunk 1"
        self.inbox.opus(1)
        self.assertEqual(self.polls(3), 0)
        self.inbox.sidecar(1)
        self.assertEqual(self.polls(2), 1)
        self.assertEqual(self.engine.calls, [f"{SID}_00000.opus", f"{SID}_00001.opus"])

    def test_changing_size_is_not_ready(self):
        final = b"OggS" + b"\x01" * 4000
        self.inbox.sidecar(0, audio=final)
        path = self.inbox.name(0, "opus")
        for size in (1000, 2000, 3000):  # grows on every poll: never stable
            path.write_bytes(final[:size])
            self.watchdog.poll_once()
        self.assertEqual(self.engine.calls, [])
        path.write_bytes(final)
        self.assertEqual(self.watchdog.poll_once(), 0, "changed since the last poll")
        self.assertEqual(self.watchdog.poll_once(), 1)

    def test_bad_sha_is_never_processed_and_logged_once(self):
        self.inbox.sidecar(0, sha="0" * 64)
        self.inbox.opus(0)
        self.assertEqual(self.polls(5), 0)
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(sum("SHA-256" in line for line in self.logs), 1)
        # A corrected sidecar (e.g. Syncthing delivers the right version) unblocks it.
        self.inbox.sidecar(0)
        self.assertEqual(self.polls(2), 1)

    def test_syncthing_temporary_files_are_ignored(self):
        (self.inbox.dir / f"~syncthing~{SID}_00000.opus.tmp").write_bytes(b"partial")
        self.inbox.sidecar(0)
        self.assertEqual(self.polls(3), 0)

    # --- ordering ------------------------------------------------------------------------

    def test_chunks_are_processed_in_seq_order(self):
        self.inbox.chunk(2)
        self.inbox.chunk(1)
        self.assertEqual(self.polls(3), 0, "seq 1 and 2 wait for seq 0")
        self.inbox.chunk(0)
        self.assertEqual(self.polls(2), 3)
        self.assertEqual(self.engine.calls, [f"{SID}_{n:05d}.opus" for n in (0, 1, 2)])

    def test_a_bad_chunk_blocks_later_ones_no_skipping(self):
        self.inbox.sidecar(0, sha="f" * 64)
        self.inbox.opus(0)
        self.inbox.chunk(1)
        self.assertEqual(self.polls(4), 0)
        self.assertEqual(self.engine.calls, [])
        self.assertEqual(self.watchdog.state.session(SID)["next_seq"], 0)
        self.assertFalse((self.outputs / "state.json").exists(), "nothing processed, nothing saved")

    def test_seqs_listed_as_failed_are_passed_over_only_with_the_manifest(self):
        self.inbox.chunk(0)
        self.inbox.chunk(2)
        self.polls(3)
        self.assertEqual(self.engine.calls, [f"{SID}_00000.opus"], "seq 2 waits for seq 1")
        self.inbox.manifest([0, 2], failed=[1])
        self.polls(2)
        self.assertEqual(self.engine.calls, [f"{SID}_00000.opus", f"{SID}_00002.opus"])
        self.assertEqual(self.state()["skipped_failed"], [1])
        self.assertTrue(self.state()["completed"])

    # --- restart -------------------------------------------------------------------------

    def test_restart_continues_without_reprocessing_or_skipping(self):
        self.inbox.chunk(0)
        self.inbox.chunk(1)
        self.polls(2)
        self.assertEqual(self.state()["next_seq"], 2)
        engine2 = FakeEngine()
        restarted = self.make(engine2)  # new process: state from disk
        self.inbox.chunk(2)
        self.polls(3, restarted)
        self.assertEqual(engine2.calls, [f"{SID}_00002.opus"])
        self.assertEqual(self.state()["next_seq"], 3)

    def test_transcript_written_before_a_crash_is_adopted_not_redone(self):
        self.inbox.chunk(0)
        self.polls(2)
        # Crash between writing the transcript and saving state: roll the state back.
        state_path = self.outputs / "state.json"
        data = json.loads(state_path.read_text())
        data["sessions"][SID] = {"next_seq": 0, "processed": {}, "skipped_failed": [], "completed": False}
        state_path.write_text(json.dumps(data))
        engine2 = FakeEngine()
        restarted = self.make(engine2)
        self.polls(2, restarted)
        self.assertEqual(engine2.calls, [])
        self.assertTrue(self.state()["processed"]["0"]["recovered"])
        self.assertEqual(self.state()["next_seq"], 1)

    def test_completed_session_is_not_redone_after_restart(self):
        self.inbox.chunk(0)
        self.inbox.manifest([0])
        self.polls(2)
        self.assertTrue(self.state()["completed"])
        engine2 = FakeEngine()
        self.polls(3, self.make(engine2))
        self.assertEqual(engine2.calls, [])

    # --- session completion --------------------------------------------------------------

    def test_manifest_before_last_chunk_waits_for_every_listed_file(self):
        self.inbox.chunk(0)
        self.inbox.chunk(1)
        self.inbox.sidecar(2)  # the last .opus is still missing
        self.inbox.manifest([0, 1, 2])
        self.polls(4)
        transcript_md = self.outputs / SID / f"{SID}_transcript.md"
        self.assertFalse(self.state()["completed"])
        self.assertFalse(transcript_md.exists())
        self.inbox.opus(2)
        self.polls(2)
        self.assertTrue(self.state()["completed"])
        session = json.loads((self.outputs / SID / f"{SID}_transcript.json").read_text())
        self.assertEqual([c["seq"] for c in session["chunks"]], [0, 1, 2])
        self.assertEqual(session["text"], "words of chunk 0 words of chunk 1 words of chunk 2")
        md = transcript_md.read_text()
        self.assertLess(md.index("chunk 0"), md.index("chunk 1"))
        self.assertIn("## Timing per chunk", md)
        self.assertEqual(session["timing_summary"]["total_ms"]["count"], 3)

    def test_session_without_manifest_is_never_complete(self):
        self.inbox.chunk(0)
        self.polls(3)
        self.assertFalse(self.state()["completed"])

    # --- read-only inbox -----------------------------------------------------------------

    def test_inbox_is_never_written(self):
        for n in range(3):
            self.inbox.chunk(n)
        self.inbox.manifest([0, 1, 2])
        before = tree(self.inbox_root)
        self.polls(3)
        self.assertTrue(self.state()["completed"])
        self.assertEqual(tree(self.inbox_root), before)

    def test_outputs_inside_the_inbox_are_refused(self):
        with self.assertRaises(ValueError):
            Watchdog(self.inbox_root, self.inbox_root / "out", self.engine)

    def test_live_run_stops_once_a_new_session_completes(self):
        already = self.watchdog.completed_sessions()
        self.inbox.chunk(0)
        self.inbox.manifest([0])
        self.watchdog.run(interval_s=0.0, stop=lambda: len(self.watchdog.completed_sessions() - already) >= 1)
        self.assertEqual(self.watchdog.completed_sessions(), {SID})

    def test_run_until_idle_drains_the_backlog(self):
        for n in range(2):
            self.inbox.chunk(n)
        self.inbox.manifest([0, 1])
        self.watchdog.run(interval_s=0.0, until_idle=True)
        self.assertEqual(len(self.engine.calls), 2)
        self.assertEqual(self.watchdog.incomplete_sessions(), [])


if __name__ == "__main__":
    unittest.main()
