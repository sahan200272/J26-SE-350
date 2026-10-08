import json
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil
import pynvml

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
    """Checks GPU and RAM use every 0.1 s in the background and keeps the peak."""

    def __init__(self, interval: float = 0.1):
        self.interval = interval
        self.peak_vram_mb = 0.0
        self.peak_ram_mb = 0.0
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
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        while not self._stop.is_set():
            used = pynvml.nvmlDeviceGetMemoryInfo(handle).used / 1024**2
            self.peak_vram_mb = max(self.peak_vram_mb, used)
            self.peak_ram_mb = max(self.peak_ram_mb, self._ollama_ram_mb())
            time.sleep(self.interval)
        pynvml.nvmlShutdown()

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()


def run_benchmark(runs: int = 5) -> dict:
    client = LLMClient()
    if not client.is_ready():
        raise SystemExit(f"Model '{client.config.model}' not found. Run: ollama pull {client.config.model}")

    client.chat("Hello")  # warm-up: loads the model so load time is not measured

    monitor = ResourceMonitor()
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
    report = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "model": client.config.model,
        "num_ctx": client.config.num_ctx,
        "runs_per_prompt": runs,
        "results": results,
        "peak_vram_mb": round(monitor.peak_vram_mb),
        "peak_ram_mb": round(monitor.peak_ram_mb),
        "checks": {
            "tpot_under_45ms": worst_mean < TPOT_LIMIT_MS,
            "vram_under_6gb": monitor.peak_vram_mb <= VRAM_LIMIT_MB,
            "ram_under_8gb": monitor.peak_ram_mb <= RAM_LIMIT_MB,
        },
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), indent=2))