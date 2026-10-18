"""Offset maths: session-relative times, clock-corrected latency, RTF, summaries."""

from __future__ import annotations

import unittest

from hub_speech_pipeline.asr import transcript
from hub_speech_pipeline.tools.verify_session import wallclock_ns

SIDECAR = {"session_id": "S", "seq": 3, "audio_file": "S_00003.opus", "sha256": "ab" * 32,
           "sample_rate": 16000, "samples": 32000, "start_ms": 15868.4, "end_ms": 17868.4,
           "start_wallclock": "2026-10-18T12:23:10.902+05:30", "end_wallclock": "2026-10-18T12:23:12.902+05:30"}


class SessionTimes(unittest.TestCase):
    def test_session_time_is_chunk_time_plus_chunk_start(self):
        segments = [{"text": " hello there ", "start": 0.25, "end": 1.5,
                     "words": [{"word": "hello", "start": 0.25, "end": 0.6, "score": 0.98765},
                               {"word": "20th", "score": None}]}]
        out = transcript.with_session_times(segments, 15868.4)
        seg = out[0]
        self.assertEqual(seg["text"], "hello there")
        self.assertEqual((seg["start"], seg["end"]), (0.25, 1.5))
        self.assertEqual((seg["session_start"], seg["session_end"]), (16.118, 17.368))
        self.assertEqual(seg["words"][0]["session_start"], 16.118)
        self.assertEqual(seg["words"][0]["session_end"], 16.468)
        self.assertEqual(seg["words"][0]["score"], 0.988)
        # Words WhisperX could not align keep no times.
        self.assertIsNone(seg["words"][1]["start"])
        self.assertIsNone(seg["words"][1]["session_start"])


class Latency(unittest.TestCase):
    def test_latency_corrects_for_the_phone_clock_offset(self):
        end_phone = wallclock_ns(SIDECAR["end_wallclock"])
        # Phone clock 15 ms behind the PC: the chunk ended at end_phone + 15 ms on the PC clock.
        written = end_phone + 2_500_000_000
        lat = transcript.latency(written, SIDECAR["end_wallclock"], {"offset_ms": -15.0, "uncertainty_ms": 11.4})
        self.assertEqual(lat["latency_ms"], 2485.0)
        self.assertEqual(lat["uncertainty_ms"], 11.9)  # + 0.5 ms for end_wallclock precision
        self.assertTrue(lat["clock_corrected"])

    def test_phone_ahead_of_pc(self):
        end_phone = wallclock_ns(SIDECAR["end_wallclock"])
        lat = transcript.latency(end_phone + 1_000_000_000, SIDECAR["end_wallclock"],
                                 {"offset_ms": 250.0, "uncertainty_ms": 5.0})
        self.assertEqual(lat["latency_ms"], 1250.0)

    def test_without_a_clock_offset_the_value_is_marked_uncorrected(self):
        end_phone = wallclock_ns(SIDECAR["end_wallclock"])
        lat = transcript.latency(end_phone + 3_000_000_000, SIDECAR["end_wallclock"], None)
        self.assertEqual(lat["latency_ms"], 3000.0)
        self.assertFalse(lat["clock_corrected"])
        self.assertIsNone(lat["uncertainty_ms"])


class Documents(unittest.TestCase):
    def doc(self, seq: int, total_ms: float, latency_ms: float, text: str) -> dict:
        sidecar = SIDECAR | {"seq": seq, "audio_file": f"S_{seq:05d}.opus"}
        segs = transcript.with_session_times([{"text": text, "start": 0.0, "end": 1.0, "words": []}],
                                             sidecar["start_ms"])
        timing = {"queue_wait_ms": 5.0, "decode_ms": 50.0, "transcribe_ms": total_ms - 150,
                  "align_ms": 100.0, "total_ms": total_ms}
        lat = {"latency_ms": latency_ms, "clock_corrected": True, "clock_offset_ms": -15.0, "uncertainty_ms": 11.9}
        return transcript.chunk_document(sidecar, segs, {"whisper_model": "base"}, timing, lat)

    def test_rtf_is_processing_time_over_audio_duration(self):
        d = self.doc(0, 500.0, 2000.0, "a")
        self.assertEqual(d["audio_duration_s"], 2.0)  # 32000 samples at 16 kHz
        self.assertEqual(d["timing"]["rtf"], 0.25)

    def test_session_documents_order_and_summary(self):
        chunks = [self.doc(1, 900.0, 3000.0, "second"), self.doc(0, 300.0, 2000.0, "first"),
                  self.doc(2, 600.0, 2500.0, "third")]
        manifest = {"session_id": "S", "pause_intervals": [{"start_ms": 1000.0, "end_ms": 6000.0, "reason": "user"}]}
        doc, md = transcript.session_documents(manifest, chunks, {"whisper_model": "base"})
        self.assertEqual([c["seq"] for c in doc["chunks"]], [0, 1, 2])
        self.assertEqual(doc["text"], "first second third")
        self.assertEqual(doc["timing_summary"]["latency_ms"], {"count": 3, "median": 2500.0, "max": 3000.0, "min": 2000.0})
        self.assertEqual(doc["timing_summary"]["total_ms"]["median"], 600.0)
        self.assertEqual(doc["timing_summary"]["session_rtf"], round(1.8 / 6.0, 4))
        self.assertLess(md.index("first"), md.index("second"))
        self.assertIn("1.0-6.0 s (user)", md)


if __name__ == "__main__":
    unittest.main()
