"""Live latency breakdown: phone-log parsing, end of speech, stage maths."""

from __future__ import annotations

import datetime as dt
import unittest

from hub_speech_pipeline.tools import live_latency as ll
from hub_speech_pipeline.tools.verify_session import ns_to_iso, wallclock_ns

TZ = dt.timezone(dt.timedelta(hours=5, minutes=30))
MS = 1_000_000

LOG = """\
10-18 12:49:00.000 I/flutter (1): [session] 20261018T124900_aaaa started 2026-10-18T12:49:00.000+05:30
10-18 12:49:05.000 I/flutter (1): [segment] #0 run 0: 0.0-4000.0 ms (audio samples 0-64000), speech ratio 0.9
10-18 12:49:06.000 I/flutter (1): [encode] #0 → 20261018T124900_aaaa_00000.opus: 1000 B from 64000 samples
10-18 12:50:02.112 I/flutter (2): [session] 20261018T125002_6c92 started 2026-10-18T12:50:02.111+05:30
10-18 12:50:11.829 I/flutter (2): [segment] #0 run 0: 1380.2-9348.2 ms (audio samples 16384-143872), speech ratio 0.82
10-18 12:50:11.830 I/flutter (2): [encode] queued #0 (queue length 1)
10-18 12:50:12.693 I/flutter (2): [encode] #0 → 20261018T125002_6c92_00000.opus: 42787 B from 127488 samples
"""

SIDECAR = {"seq": 0, "samples": 127488, "frames": 249, "sample_rate": 16000, "start_ms": 1380.213,
           "end_ms": 9348.213, "end_wallclock": "2026-10-18T12:50:11.459+05:30", "forced_split": False,
           "segmenter": {"config": {"post_roll_frames": 8}}, "processing": {"encode_ms": 796.2}}


class PhoneLog(unittest.TestCase):
    def test_times_are_attributed_to_the_right_session(self):
        times = ll.phone_log_times(LOG, "20261018T125002_6c92", 2026, TZ)
        self.assertEqual(set(times), {0})
        self.assertEqual(times[0]["cut"], wallclock_ns("2026-10-18T12:50:11.829+05:30"))
        self.assertEqual(times[0]["published"], wallclock_ns("2026-10-18T12:50:12.693+05:30"))
        other = ll.phone_log_times(LOG, "20261018T124900_aaaa", 2026, TZ)
        self.assertEqual(other[0]["cut"], wallclock_ns("2026-10-18T12:49:05.000+05:30"))


class EndOfSpeech(unittest.TestCase):
    def test_hangover_subtracts_the_post_roll(self):
        eos, how = ll.end_of_speech_ns(SIDECAR, session_end_ms=27849.5)
        # 127488 samples / 249 frames = 512 samples = 32 ms per frame; 8 frames = 256 ms.
        self.assertEqual(eos, wallclock_ns(SIDECAR["end_wallclock"]) - 256 * MS)
        self.assertIn("hangover", how)

    def test_forced_split_and_stop_use_the_chunk_end(self):
        end = wallclock_ns(SIDECAR["end_wallclock"])
        self.assertEqual(ll.end_of_speech_ns(SIDECAR | {"forced_split": True}, 27849.5)[0], end)
        eos, how = ll.end_of_speech_ns(SIDECAR, session_end_ms=SIDECAR["end_ms"] + 100)
        self.assertEqual((eos, how), (end, "flushed by Stop"))


class Stages(unittest.TestCase):
    def test_stages_sum_to_the_total_and_the_offset_is_applied(self):
        offset_ms = -20.0  # phone 20 ms behind the PC: pc = phone + 20 ms
        phone = {"cut": wallclock_ns("2026-10-18T12:50:11.829+05:30"),
                 "published": wallclock_ns("2026-10-18T12:50:12.693+05:30")}
        arrival = phone["published"] + 20 * MS + 1500 * MS  # 1.5 s Syncthing delivery, in PC time
        ready = arrival + 240 * MS
        start = ready + 1 * MS
        written = start + 4000 * MS
        hub = {"arrival": {"ready_pc": ns_to_iso(ready), "processing_started_pc": ns_to_iso(start)},
               "latency": {"transcript_written_pc": ns_to_iso(written)}}
        row = ll.stages(SIDECAR, phone, arrival, hub, offset_ms, session_end_ms=27849.5)
        self.assertEqual(row["vad_wait"], 626.0)  # 11.829 - (11.459 - 0.256)
        self.assertEqual(row["encode"], 864.0)
        self.assertEqual(row["delivery"], 1500.0)
        self.assertEqual(row["pc_detect"], 240.0)
        self.assertEqual(row["pc_queue"], 1.0)
        self.assertEqual(row["asr"], 4000.0)
        self.assertEqual(row["stage_sum"], row["total"])
        self.assertEqual(row["total"], 626 + 864 + 1500 + 240 + 1 + 4000)
        self.assertEqual(row["from_chunk_end"], row["total"] - 256)


if __name__ == "__main__":
    unittest.main()
