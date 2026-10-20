"""The seven Component 2 objectives, their targets and how to read their result files.

Targets live only here. The HTML page gets every number from /api/status.
Each extractor only reads the file; the decision is made in status.evaluate.
"""

from __future__ import annotations

from typing import Any

from scripts.panel_dashboard.status import Objective, Reading

REQUIRED_VECTORS = 50


def _date(text: Any) -> str:
    return str(text).replace("T", " ")


def _rp16_machine(env: dict[str, Any]) -> str:
    return f"{env['os']}, {env['cpu_threads']} CPU threads, Python {env['python']}"


def _rp12_machine(hw: dict[str, Any]) -> str:
    gpu = "NVIDIA GPU" if hw.get("nvidia_gpu_found") is True else "no NVIDIA GPU"
    return f"{hw['os']}, {hw['cpu_threads']} CPU threads, {hw['total_ram_gb']} GB RAM, {gpu}"


def _note(data: dict[str, Any], field: str = "note") -> tuple[str, ...]:
    text = data.get(field)
    return (f"From result file: {text}",) if isinstance(text, str) and text else ()


def read_tool_latency(data: dict[str, Any]) -> Reading:
    summary = data["summary"]
    if not summary:
        raise ValueError("empty summary")
    worst_ms = max(float(tool["max_ms"]) for tool in summary.values())
    calls = sum(int(tool["calls"]) for tool in summary.values())
    failures = data.get("failures")
    not_valid = None
    if data.get("valid") is not True:
        not_valid = "The run is marked not valid in the result file."
    elif failures != 0:
        not_valid = f"{failures} call(s) failed during the run."
    return Reading(
        value=worst_ms / 1000.0,
        shown=f"{worst_ms:.1f} ms slowest single call ({calls} calls over {len(summary)} tools)",
        machine=_rp16_machine(data["environment"]),
        date=_date(data["measured_at"]),
        not_valid=not_valid,
        file_limits=_note(data),
    )


def read_sandbox_escape(data: dict[str, Any]) -> Reading:
    vectors = data["vectors"]
    run = data["vectors_run"]
    escaped = data["escaped_vector_ids"]
    rate = data["escape_rate"]
    if not isinstance(escaped, list) or not isinstance(vectors, int) or vectors <= 0:
        raise TypeError("bad escape result shape")
    not_valid = None
    if data.get("official") is not True:
        not_valid = "Not an official run (the frozen dataset was not used)."
    elif vectors != REQUIRED_VECTORS or run != vectors:
        not_valid = f"{run} of {vectors} vectors run; the target needs all {REQUIRED_VECTORS}."
    elif (len(escaped) == 0) != (rate == 0):
        not_valid = "Escape rate and list of escaped vectors disagree."
    percent = 100.0 * len(escaped) / vectors
    fingerprint = str(data.get("dataset_fingerprint", ""))
    limits = _note(data)
    if fingerprint:
        limits += (f"Dataset fingerprint {fingerprint[:8]}...{fingerprint[-6:]} (frozen before the harness).",)
    return Reading(
        value=percent,
        shown=f"{percent:.1f}% ({len(escaped)} of {vectors} vectors escaped)",
        machine=_rp16_machine(data["environment"]),
        date=_date(data["measured_at"]),
        not_valid=not_valid,
        file_limits=limits,
    )


def read_tpot(data: dict[str, Any]) -> Reading:
    hw = data["hardware"]
    worst = float(data["worst_mean_tpot_ms"])
    mode = str(data.get("mode", ""))
    not_valid = None
    if hw.get("nvidia_gpu_found") is not True or "cpu-only" in mode.lower():
        not_valid = f"CPU-only baseline ({worst:.1f} ms); the target needs the GPU machine."
    return Reading(
        value=worst,
        shown=f"{worst:.1f} ms worst mean TPOT, {data['model']} (CPU baseline only)"
        if not_valid
        else f"{worst:.1f} ms worst mean TPOT, {data['model']}",
        machine=_rp12_machine(hw),
        date=_date(data["date"]),
        not_valid=not_valid,
        file_limits=_note(data, "mode"),
    )


def read_vram(data: dict[str, Any]) -> Reading:
    hw = data["hardware"]
    vram_mb = data["peak_vram_mb"]
    checked = data["checks"].get("vram_under_6gb")
    source = data.get("vram_source", "unknown source")
    not_valid = None
    if hw.get("nvidia_gpu_found") is not True:
        not_valid = "No NVIDIA GPU found; the 0 MB reading is not a VRAM measurement."
    elif checked is None:
        not_valid = "The benchmark did not check VRAM."
    elif not isinstance(vram_mb, (int, float)) or isinstance(vram_mb, bool) or vram_mb <= 0:
        not_valid = "No VRAM use was recorded on the GPU."
    value = vram_mb / 1024.0 if isinstance(vram_mb, (int, float)) and not isinstance(vram_mb, bool) else None
    return Reading(
        value=value,
        shown=f"{vram_mb} MB peak ({source})",
        machine=_rp12_machine(hw),
        date=_date(data["date"]),
        not_valid=not_valid,
        file_limits=_note(data, "mode"),
    )


OBJECTIVES: list[Objective] = [
    Objective(
        key="schema_compliance",
        name="JSON schema compliance",
        op=">=", target=98, unit="%",
        evidence=None, extract=None,
        limits=("Planned: 200 prompts on the GPU machine (another story).",),
    ),
    Objective(
        key="intent_f1",
        name="Intent F1",
        op=">=", target=90, unit="%",
        evidence=None, extract=None,
        limits=("Planned on the GPU machine (another story).",),
    ),
    Objective(
        key="tool_latency",
        name="Tool-call latency (NFR-01)",
        op="<", target=1.5, unit="s",
        evidence="rp16_tool_latency_laptop.json", extract=read_tool_latency,
        limits=(
            "Tool layer only: the 20 to 90 s LLM step is a different metric and is not included.",
            "Starting both servers takes about 4 s once per session; not counted per call.",
        ),
    ),
    Objective(
        key="tpot",
        name="Time per output token (TPOT)",
        op="<", target=45, unit="ms",
        evidence="rp12_llm_benchmark.json", extract=read_tpot,
        limits=("Must be measured on the GPU machine.",),
    ),
    Objective(
        key="vram",
        name="Peak VRAM",
        op="<=", target=6, unit="GB",
        evidence="rp12_llm_benchmark.json", extract=read_vram,
        limits=("Must be measured on the GPU machine.",),
    ),
    Objective(
        key="sandbox_escape",
        name=f"Sandbox escape rate ({REQUIRED_VECTORS} vectors)",
        op="==", target=0.0, unit="%",
        evidence="rp16_path_traversal_results.json", extract=read_sandbox_escape,
        limits=(
            "Zero failures in 50 only suggests a true failure rate below about 6% (rule of three).",
            "40 of 50 vectors were written by the author of the guard; 10 follow public examples.",
            "Only 2 vectors reached the filesystem checks; junctions and 8.3 short names not covered.",
        ),
    ),
    Objective(
        key="sus",
        name="System Usability Scale (SUS)",
        op=">=", target=75, unit="",
        evidence=None, extract=None,
        limits=("Needs a user study; not run yet.",),
    ),
]
