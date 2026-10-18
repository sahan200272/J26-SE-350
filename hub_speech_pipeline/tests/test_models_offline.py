"""Model availability check (clear failure, no download) and offline enforcement."""

from __future__ import annotations

import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hub_speech_pipeline.asr import models
from hub_speech_pipeline.common import offline


class ModelCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hf = Path(self.tmp.name, "hf")
        self.torch = Path(self.tmp.name, "torch")

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_cache_names_every_missing_file_and_the_setup_command(self):
        missing = models.missing_files("base", hf_cache=self.hf, hub_dir=self.torch)
        self.assertEqual(len(missing), 5)  # 4 faster-whisper files + the aligner
        self.assertTrue(any("model.bin" in m for m in missing))
        self.assertTrue(any("wav2vec2_fairseq_base_ls960_asr_ls960.pth" in m for m in missing))
        with self.assertRaises(models.ModelMissingError) as ctx:
            models.require_models("base", hf_cache=self.hf, hub_dir=self.torch)
        self.assertIn("setup_models --download base", str(ctx.exception))

    def test_complete_cache_passes_and_wrong_sizes_fail(self):
        tiny = models.WhisperModelSpec("tiny-test", "Org/tiny", "c0ffee" * 6 + "abcd",
                                       {"config.json": 3, "model.bin": 5})
        align = models.AlignModelSpec("en", "B", "align.pth", "https://example.invalid/align.pth", 4)
        with mock.patch.dict(models.WHISPER_MODELS, {"tiny-test": tiny}), \
                mock.patch.dict(models.ALIGN_MODELS, {"en": align}):
            snap = models.whisper_snapshot(tiny, self.hf)
            snap.mkdir(parents=True)
            (snap / "config.json").write_bytes(b"{}\n")
            (snap / "model.bin").write_bytes(b"12345")
            ref = snap.parent.parent / "refs" / "main"
            ref.parent.mkdir(parents=True)
            ref.write_text(tiny.revision)
            ckpt = models.align_checkpoint(align, self.torch)
            ckpt.parent.mkdir(parents=True)
            ckpt.write_bytes(b"1234")
            self.assertEqual(models.missing_files("tiny-test", hf_cache=self.hf, hub_dir=self.torch), [])
            (snap / "model.bin").write_bytes(b"123")  # truncated download
            ref.write_text("another-revision")
            missing = models.missing_files("tiny-test", hf_cache=self.hf, hub_dir=self.torch)
            self.assertEqual(len(missing), 2)
            self.assertTrue(any("has 3 B, expected 5 B" in m for m in missing))
            self.assertTrue(any("refs/main" in m for m in missing))

    def test_unknown_model(self):
        with self.assertRaises(ValueError):
            models.missing_files("huge")

    def test_cache_locations_follow_the_environment(self):
        with mock.patch.dict(os.environ, {"HF_HUB_CACHE": str(self.hf), "TORCH_HOME": str(self.torch)}):
            self.assertEqual(models.hf_hub_cache(), self.hf)
            self.assertEqual(models.torch_hub_dir(), self.torch / "hub")


class Offline(unittest.TestCase):
    def setUp(self):
        self.saved_env = {k: os.environ.get(k) for k in offline.OFFLINE_ENV}

    def tearDown(self):
        offline._uninstall_for_tests()
        for k, v in self.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_environment_is_set(self):
        env = offline.enforce_offline()
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(os.environ["PYANNOTE_METRICS_ENABLED"], "false")

    def test_non_loopback_connections_are_refused_and_counted(self):
        offline.enforce_offline()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            with self.assertRaises(offline.OfflineViolation):
                s.connect(("203.0.113.7", 443))  # TEST-NET-3: never reached
        with self.assertRaises(offline.OfflineViolation):
            socket.create_connection(("example.org", 80), timeout=1)
        self.assertEqual(len(offline.blocked_attempts()), 2)

    def test_loopback_is_allowed(self):
        offline.enforce_offline()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            with socket.create_connection(server.getsockname(), timeout=2):
                pass
        self.assertEqual(offline.blocked_attempts(), [])


if __name__ == "__main__":
    unittest.main()
