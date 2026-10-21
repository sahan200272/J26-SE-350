"""The seven Component 2 objectives, their targets and how to read their result files.

Targets live only here. The HTML page gets every number from /api/status.
Each extractor only reads the file; the decision is made in status.evaluate.
"""

from __future__ import annotations

from typing import Any

from agentic_core.tests.schema_compliance.frozen_setup import FROZEN_SETUP_HASHES
from agentic_core.tests.schema_compliance.test_case_dataset import FROZEN_FINGERPRINT as SCHEMA_CASES_FINGERPRINT
from scripts.panel_dashboard.status import Objective, Reading

REQUIRED_VECTORS = 50
REQUIRED_SCHEMA_CASES = 200


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


def _pct(value: Any) -> str:
    return f"{100.0 * float(value):.1f}%"


def _schema_run_problem(data: dict[str, Any], mode: str) -> str | None:
    """Why a schema-compliance result file does not count, or None if it does."""
    total = data["summary"]["total"]
    records = data["records"]
    if not isinstance(records, list):
        raise TypeError("records must be a list")
    if data.get("mode") != mode:
        return f"This file is the {data.get('mode')} run, not the {mode} run."
    if data.get("official") is not True:
        return "Not an official run (frozen cases or frozen setup not used)."
    if data.get("dataset_fingerprint") != SCHEMA_CASES_FINGERPRINT:
        return "Dataset fingerprint does not match the frozen 200 cases."
    if data.get("setup_frozen") is not True or data.get("setup_hashes") != FROZEN_SETUP_HASHES:
        return "Prompt, schema or LLM config differ from the frozen setup."
    if (data.get("all_run") is not True or data["cases"] != REQUIRED_SCHEMA_CASES
            or total["cases_run"] != REQUIRED_SCHEMA_CASES or len(records) != REQUIRED_SCHEMA_CASES):
        return f"{total['cases_run']} of {data['cases']} cases ran; the target needs all {REQUIRED_SCHEMA_CASES}."
    if total["infra_errors"] != 0:
        return f"{total['infra_errors']} case(s) hit an Ollama error."
    if total.get("extractor_disagrees", 0) != 0:
        return "The extractor and the check disagree on some cases."
    counted = sum(1 for r in records if r.get("status") == "ran" and r.get("compliant") is True)
    if counted != total["compliant"] or abs(float(total["rate"]) - counted / REQUIRED_SCHEMA_CASES) > 1e-9:
        return "Summary numbers and per-case records disagree."
    return None


def read_schema_compliance(data: dict[str, Any]) -> Reading:
    total = data["summary"]["total"]
    rate = float(total["rate"])
    machine = data["machine"]
    placement = data["model_placement_after_first_case"]["placement"]
    fingerprint = str(data["dataset_fingerprint"])
    errors = total.get("error_type_counts") or {}
    limits = _note(data) + (
        f"JSON syntax valid {total['json_valid']} of {total['cases_run']}; "
        f"cut off at {data['llm_options']['num_predict']} tokens: {total['cut_off']}.",
        "Failures by error type: " + (", ".join(f"{k} {v}" for k, v in sorted(errors.items())) or "none") + ".",
        f"Dataset fingerprint {fingerprint[:8]}...{fingerprint[-6:]} (frozen before the runner).",
    )
    return Reading(
        value=100.0 * rate,
        shown=f"{_pct(rate)} ({total['compliant']} of {total['cases_run']} first answers valid; "
              f"95% CI {_pct(total['ci95_low'])} to {_pct(total['ci95_high'])})",
        machine=f"{machine['gpu']}; {data['model']} at {placement}; {machine['os']}",
        date=_date(data["measured_at"]),
        not_valid=_schema_run_problem(data, "grammar"),
        file_limits=limits,
    )


def describe_schema_baseline(data: dict[str, Any]) -> str:
    problem = _schema_run_problem(data, "baseline")
    if problem is not None:
        return f"Baseline file not shown: {problem}"
    total = data["summary"]["total"]
    return (f"Comparison only, no target: grammar OFF on the same 200 cases gave "
            f"{_pct(total['rate'])} ({total['compliant']} of {total['cases_run']}; "
            f"95% CI {_pct(total['ci95_low'])} to {_pct(total['ci95_high'])}; "
            f"JSON syntax valid {total['json_valid']} of {total['cases_run']}).")


OBJECTIVES: list[Objective] = [
    Objective(
        key="schema_compliance",
        name="JSON schema compliance (NFR-04)",
        op=">=", target=98, unit="%",
        evidence="schema_compliance_official.json", extract=read_schema_compliance,
        limits=(
            "Valid = the first answer parses as JSON and passes DraftPlan; prefilter off; no retry.",
            "Measures valid structure only, not correct content (Intent F1 measures that).",
            "The JSON-RPC 2.0 envelope is built by the FastMCP client, not the LLM; not part of this number.",
            "The HH:MM time rule is checked in Python only, not by the grammar.",
            "Synthetic cases prepared for this test and reviewed by the author; not real meetings.",
            "200 cases is a small sample; see the 95% confidence interval.",
            "RTX 2050 4 GB with the model split between CPU and GPU. Validity should not depend on "
            "speed, but CPU and GPU maths can differ slightly, so another machine may give other answers.",
        ),
        comparisons=(("schema_compliance_baseline.json", describe_schema_baseline),),
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
