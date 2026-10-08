import json
import os
import platform
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil

try:
    import pynvml
except Exception:
    pynvml = None

from .client import LLMClient

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_FILE = REPO_ROOT / "docs" / "evaluation" / "rp12_llm_benchmark.json"

SAMPLE = (
    "Speaker 1: Let's review the design on Monday.\n"
    "Speaker 2: I'll send the draft to Nimal by Friday.\n"
)
PROMPTS = {
    "short": "Summarize in one sentence: we should meet on Friday to review the budget.",
    "medium": "Summarize this meeting in 3 bullet points:\n" + SAMPLE * 8,
    "long": "Summarize this meeting in 3 bullet points:\n" + SAMPLE * 40,
}

VRAM_LIMIT_MB = 6 * 1024
RAM_LIMIT_MB = 8 * 1024
TPOT_LIMIT_MS = 45


class ResourceMonitor:
    """Watches memory in the background and keeps the highest values."""

    def __init__(self, client: LLMClient, interval: float = 0.2):
        self.client = client._client
        self.interval = interval
        self.peak_gpu_mb = 0.0          # whole GPU (NVIDIA only)
        self.peak_model_vram_mb = 0.0   # model memory on the GPU (from Ollama)
        self.peak_model_size_mb = 0.0   # total model memory (GPU + CPU parts)
        self.peak_ram_mb = 0.0          # RAM used by Ollama programs
        self.nvml_ok = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @staticmethod
    def _ollama_ram_mb() -> float:
        total = 0
        for p in psutil.process_iter(["name", "memory_info"]):
            name = (p.info["name"] or "").lower()
            if "ollama" in name and p.info["memory_info"]:
                total += p.info["memory_info"].rss
        return total / 1024**2

    def _run(self):
        handle = None
        try:
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.nvml_ok = True
        except Exception:
            pass  # no NVIDIA driver: carry on without it

        while not self._stop.is_set():
            if handle is not None:
                used = pynvml.nvmlDeviceGetMemoryInfo(handle).used / 1024**2
                self.peak_gpu_mb = max(self.peak_gpu_mb, used)
            try:
                for m in self.client.ps().models:
                    self.peak_model_vram_mb = max(
                        self.peak_model_vram_mb, (m.size_vram or 0) / 1024**2
                    )
                    self.peak_model_size_mb = max(
                        self.peak_model_size_mb, (m.size or 0) / 1024**2
                    )
            except Exception:
                pass
            self.peak_ram_mb = max(self.peak_ram_mb, self._ollama_ram_mb())
            time.sleep(self.interval)

        if self.nvml_ok:
            pynvml.nvmlShutdown()

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()


def run_benchmark(runs: int = 5) -> dict:
    client = LLMClient()
    client.is_ready()
    client.chat("Hello")  # warm-up: loads the model so load time is not measured

    monitor = ResourceMonitor(client)
    monitor.start()
    results = {}
    for name, prompt in PROMPTS.items():
        tpots = [client.chat(prompt).tpot_ms for _ in range(runs)]
        results[name] = {
            "mean_tpot_ms": round(statistics.mean(tpots), 2),
            "max_tpot_ms": round(max(tpots), 2),
        }
    monitor.stop()

    worst_mean = max(r["mean_tpot_ms"] for r in results.values())
    on_gpu = monitor.peak_model_vram_mb > 0
    ram_measured = monitor.peak_ram_mb > 0
    vram_mb = monitor.peak_gpu_mb if monitor.nvml_ok else monitor.peak_model_vram_mb

    report = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "mode": "GPU" if on_gpu else "CPU-only (baseline, not valid for the GPU targets)",
        "model": client.config.model,
        "num_ctx": client.config.num_ctx,
        "runs_per_prompt": runs,
        "results": results,
        "worst_mean_tpot_ms": worst_mean,
        "approx_tokens_per_second": round(1000 / worst_mean, 1) if worst_mean else 0,
        "peak_vram_mb": round(vram_mb),
        "vram_source": "nvml (whole GPU)" if monitor.nvml_ok else "ollama ps (model only)",
        "peak_model_size_mb": round(monitor.peak_model_size_mb),
        "peak_ram_mb": round(monitor.peak_ram_mb),
        "hardware": {
            "os": platform.platform(),
            "cpu_threads": os.cpu_count(),
            "total_ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
            "nvidia_gpu_found": monitor.nvml_ok,
        },
        # true = passed, false = failed, null = could not be tested on this machine
        "checks": {
            "tpot_under_45ms": worst_mean < TPOT_LIMIT_MS,
            "vram_under_6gb": (vram_mb <= VRAM_LIMIT_MB) if on_gpu else None,
            "ram_under_8gb": (monitor.peak_ram_mb <= RAM_LIMIT_MB) if ram_measured else None,
        },
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), indent=2))