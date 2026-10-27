"""Tests for the PP1 panel dashboard status logic (scripts/panel_dashboard)."""

import copy
import json
import threading
import urllib.request
from pathlib import Path

import pytest

from agentic_core.tests.schema_compliance.frozen_setup import FROZEN_SETUP_HASHES
from agentic_core.tests.schema_compliance.harness import wilson_interval
from agentic_core.tests.schema_compliance.test_case_dataset import FROZEN_FINGERPRINT
from scripts.panel_dashboard.objectives import OBJECTIVES
from scripts.panel_dashboard.server import build_status, make_server
from scripts.panel_dashboard.status import MET, NOT_MEASURED, NOT_MET, evaluate

BY_KEY = {objective.key: objective for objective in OBJECTIVES}
ENV = {"python": "3.12.4", "os": "Windows-11", "cpu_threads": 16, "fastmcp": "4.1.1"}


def latency_file(**changes):
    data = {
        "measured_at": "2026-10-18T20:23:22",
        "valid": True,
        "failures": 0,
        "summary": {
            "write_note": {"calls": 50, "median_ms": 5.9, "p95_ms": 7.2, "max_ms": 7.8},
            "create_event": {"calls": 50, "median_ms": 3.8, "p95_ms": 4.6, "max_ms": 4.8},
        },
        "environment": ENV,
        "note": "synthetic data, no LLM, in-memory calendar",
    }
    data.update(changes)
    return data


def escape_file(**changes):
    data = {
        "measured_at": "2026-10-19T07:51:28",
        "official": True,
        "dataset_fingerprint": "f32ddcd869d4a14b380724a7f3fccc65aa8ef48cf3ab47e9708422c4d3a449f5",
        "vectors": 50,
        "vectors_run": 50,
        "escaped_vector_ids": [],
        "escape_rate": 0.0,
        "environment": ENV,
        "note": "in-process MCP transport",
    }
    data.update(changes)
    return data


def llm_file(gpu=False, vram_mb=0, vram_check=None, tpot=229.36, mode="CPU-only (baseline)"):
    return {
        "date": "2026-10-08T17:25:20",
        "mode": mode,
        "model": "llama3:8b",
        "worst_mean_tpot_ms": tpot,
        "peak_vram_mb": vram_mb,
        "vram_source": "ollama ps (model only)",
        "hardware": {"os": "Windows-11", "cpu_threads": 16, "total_ram_gb": 7.3,
                     "nvidia_gpu_found": gpu},
        "checks": {"tpot_under_45ms": tpot < 45, "vram_under_6gb": vram_check},
    }


def schema_file(compliant=193, mode="grammar", **changes):
    low, high = wilson_interval(compliant, 200)
    data = {
        "measured_at": "2026-10-20T20:45:47",
        "official": True,
        "mode": mode,
        "dataset_fingerprint": FROZEN_FINGERPRINT,
        "cases": 200,
        "all_run": True,
        "setup_frozen": True,
        "setup_hashes": dict(FROZEN_SETUP_HASHES),
        "model": "llama3:8b",
        "llm_options": {"num_ctx": 4096, "temperature": 0.0, "num_predict": 512},
        "model_placement_after_first_case": {"placement": "56%/44% CPU/GPU"},
        "machine": {"gpu": "NVIDIA GeForce RTX 2050, 4096 MiB", "os": "Windows-11"},
        "summary": {"total": {
            "cases_run": 200, "infra_errors": 0, "compliant": compliant, "json_valid": 200,
            "schema_valid": compliant, "cut_off": 0, "extractor_disagrees": 0,
            "rate": compliant / 200, "ci95_low": low, "ci95_high": high,
            "error_type_counts": {"value_error": 200 - compliant} if compliant < 200 else {},
        }},
        "records": [{"status": "ran", "compliant": i < compliant} for i in range(200)],
        "note": "prefilter off; first answer only",
    }
    data.update(changes)
    return data


def write(folder, objective_key, data):
    path = folder / BY_KEY[objective_key].evidence
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


# --- missing or broken evidence -------------------------------------------


@pytest.mark.parametrize("key", ["schema_compliance", "tool_latency", "sandbox_escape", "tpot", "vram"])
def test_missing_file_gives_not_measured(tmp_path, key):
    row = evaluate(BY_KEY[key], tmp_path)
    assert row["status"] == NOT_MEASURED
    assert "not found" in row["reason"]
    assert row["measured"] == "-"


@pytest.mark.parametrize("key", ["intent_f1", "sus"])
def test_objective_without_result_file_is_not_measured(tmp_path, key):
    row = evaluate(BY_KEY[key], tmp_path)
    assert row["status"] == NOT_MEASURED
    assert row["evidence"] == "-"


def test_bad_json_gives_not_measured(tmp_path):
    write(tmp_path, "tool_latency", "{ not json")
    assert evaluate(BY_KEY["tool_latency"], tmp_path)["status"] == NOT_MEASURED


def test_missing_field_gives_not_measured(tmp_path):
    data = latency_file()
    del data["summary"]
    write(tmp_path, "tool_latency", data)
    assert evaluate(BY_KEY["tool_latency"], tmp_path)["status"] == NOT_MEASURED


def test_null_number_gives_not_measured(tmp_path):
    data = latency_file()
    data["summary"]["write_note"]["max_ms"] = None
    write(tmp_path, "tool_latency", data)
    assert evaluate(BY_KEY["tool_latency"], tmp_path)["status"] == NOT_MEASURED


# --- tool latency ----------------------------------------------------------


def test_latency_under_target_is_met_with_evidence(tmp_path):
    write(tmp_path, "tool_latency", latency_file())
    row = evaluate(BY_KEY["tool_latency"], tmp_path)
    assert row["status"] == MET
    assert row["target"] == "< 1.5 s"
    assert "7.8 ms" in row["measured"]
    assert row["evidence"] == "rp16_tool_latency_laptop.json"
    assert row["date"] == "2026-10-18 20:23:22"
    assert "Windows-11" in row["machine"]
    assert any("synthetic data" in limit for limit in row["limits"])


def test_latency_over_target_is_not_met(tmp_path):
    data = latency_file()
    data["summary"]["write_note"]["max_ms"] = 1500.0
    write(tmp_path, "tool_latency", data)
    assert evaluate(BY_KEY["tool_latency"], tmp_path)["status"] == NOT_MET


@pytest.mark.parametrize("changes", [{"valid": False}, {"failures": 2}])
def test_latency_invalid_run_is_not_measured(tmp_path, changes):
    write(tmp_path, "tool_latency", latency_file(**changes))
    assert evaluate(BY_KEY["tool_latency"], tmp_path)["status"] == NOT_MEASURED


# --- sandbox escape --------------------------------------------------------


def test_zero_escapes_over_50_vectors_is_met(tmp_path):
    write(tmp_path, "sandbox_escape", escape_file())
    row = evaluate(BY_KEY["sandbox_escape"], tmp_path)
    assert row["status"] == MET
    assert row["measured"].startswith("0.0%")


def test_one_escape_is_not_met(tmp_path):
    write(tmp_path, "sandbox_escape", escape_file(escaped_vector_ids=["PT-07"], escape_rate=0.02))
    assert evaluate(BY_KEY["sandbox_escape"], tmp_path)["status"] == NOT_MET


@pytest.mark.parametrize("changes", [
    {"official": False},
    {"vectors_run": 49},
    {"vectors": 40, "vectors_run": 40},
    {"escape_rate": 0.02},  # disagrees with an empty escaped list
])
def test_incomplete_or_unofficial_escape_run_is_not_measured(tmp_path, changes):
    write(tmp_path, "sandbox_escape", escape_file(**changes))
    assert evaluate(BY_KEY["sandbox_escape"], tmp_path)["status"] == NOT_MEASURED


# --- schema compliance (NFR-04) --------------------------------------------


def test_schema_compliance_below_98_is_not_met_with_interval(tmp_path):
    write(tmp_path, "schema_compliance", schema_file(193))
    row = evaluate(BY_KEY["schema_compliance"], tmp_path)
    assert row["status"] == NOT_MET
    assert row["measured"].startswith("96.5% (193 of 200")
    assert "95% CI 93.0% to 98.3%" in row["measured"]
    assert "RTX 2050" in row["machine"] and "56%/44% CPU/GPU" in row["machine"]
    assert row["date"] == "2026-10-20 20:45:47"
    assert any("Synthetic cases" in limit for limit in row["limits"])
    assert any("value_error 7" in limit for limit in row["limits"])


def test_schema_compliance_at_or_above_98_is_met(tmp_path):
    write(tmp_path, "schema_compliance", schema_file(196))
    assert evaluate(BY_KEY["schema_compliance"], tmp_path)["status"] == MET


def _broken_records(data):
    data["records"][0]["compliant"] = False  # summary still says 193
    return data


@pytest.mark.parametrize("change", [
    lambda d: d.update(official=False),
    lambda d: d.update(mode="baseline"),
    lambda d: d.update(all_run=False),
    lambda d: d.update(dataset_fingerprint="0" * 64),
    lambda d: d.update(setup_frozen=False),
    lambda d: d["setup_hashes"].update(system_prompt="0" * 64),
    lambda d: d["summary"]["total"].update(cases_run=199),
    lambda d: d.update(records=d["records"][:199]),
    lambda d: d["summary"]["total"].update(infra_errors=1),
    lambda d: d["summary"]["total"].update(extractor_disagrees=1),
    _broken_records,
], ids=["not_official", "baseline_file", "not_all_run", "fingerprint", "setup_not_frozen",
        "setup_changed", "199_run", "199_records", "infra_error", "extractor_disagrees",
        "records_disagree"])
def test_invalid_schema_compliance_run_is_not_measured(tmp_path, change):
    data = copy.deepcopy(schema_file(196))  # would be MET if it counted
    change(data)
    write(tmp_path, "schema_compliance", data)
    assert evaluate(BY_KEY["schema_compliance"], tmp_path)["status"] == NOT_MEASURED


def test_baseline_is_shown_as_comparison_and_never_changes_the_status(tmp_path):
    write(tmp_path, "schema_compliance", schema_file(193))
    (tmp_path / "schema_compliance_baseline.json").write_text(
        json.dumps(schema_file(95, mode="baseline")), encoding="utf-8")
    row = evaluate(BY_KEY["schema_compliance"], tmp_path)
    assert row["status"] == NOT_MET
    assert any(limit.startswith("Comparison only, no target") and "47.5%" in limit for limit in row["limits"])


def test_missing_or_bad_baseline_only_adds_a_note(tmp_path):
    write(tmp_path, "schema_compliance", schema_file(196))
    row = evaluate(BY_KEY["schema_compliance"], tmp_path)
    assert row["status"] == MET
    assert "Comparison file not found: schema_compliance_baseline.json" in row["limits"]
    (tmp_path / "schema_compliance_baseline.json").write_text(
        json.dumps(schema_file(95, mode="baseline", official=False)), encoding="utf-8")
    row = evaluate(BY_KEY["schema_compliance"], tmp_path)
    assert row["status"] == MET
    assert any(limit.startswith("Baseline file not shown") for limit in row["limits"])


def test_committed_official_result_shows_on_the_panel():
    """The real result file in docs/evaluation, as the panel will show it."""
    eval_dir = Path(__file__).resolve().parents[2] / "docs" / "evaluation"
    row = evaluate(BY_KEY["schema_compliance"], eval_dir)
    assert row["status"] == NOT_MET
    assert row["measured"].startswith("96.5% (193 of 200")
    assert any("47.5%" in limit for limit in row["limits"])


# --- TPOT and VRAM ---------------------------------------------------------


def test_cpu_only_tpot_is_not_measured_but_shows_baseline(tmp_path):
    write(tmp_path, "tpot", llm_file())
    row = evaluate(BY_KEY["tpot"], tmp_path)
    assert row["status"] == NOT_MEASURED
    assert "229.4 ms" in row["measured"]
    assert "GPU" in row["reason"]


def test_gpu_tpot_is_compared_with_target(tmp_path):
    write(tmp_path, "tpot", llm_file(gpu=True, tpot=30.0, mode="GPU"))
    assert evaluate(BY_KEY["tpot"], tmp_path)["status"] == MET
    write(tmp_path, "tpot", llm_file(gpu=True, tpot=60.0, mode="GPU"))
    assert evaluate(BY_KEY["tpot"], tmp_path)["status"] == NOT_MET


def test_zero_vram_without_gpu_is_never_met(tmp_path):
    write(tmp_path, "vram", llm_file(gpu=False, vram_mb=0, vram_check=None))
    assert evaluate(BY_KEY["vram"], tmp_path)["status"] == NOT_MEASURED


def test_vram_null_check_is_not_measured(tmp_path):
    write(tmp_path, "vram", llm_file(gpu=True, vram_mb=5000, vram_check=None, mode="GPU"))
    assert evaluate(BY_KEY["vram"], tmp_path)["status"] == NOT_MEASURED


def test_vram_on_gpu_is_compared_with_target(tmp_path):
    write(tmp_path, "vram", llm_file(gpu=True, vram_mb=5500, vram_check=True, mode="GPU"))
    assert evaluate(BY_KEY["vram"], tmp_path)["status"] == MET
    write(tmp_path, "vram", llm_file(gpu=True, vram_mb=7000, vram_check=False, mode="GPU"))
    assert evaluate(BY_KEY["vram"], tmp_path)["status"] == NOT_MET


# --- whole page ------------------------------------------------------------


def test_empty_folder_shows_every_objective_as_not_measured(tmp_path):
    rows = build_status(tmp_path)["rows"]
    assert len(rows) == 7
    assert {row["status"] for row in rows} == {NOT_MEASURED}


def test_server_serves_page_and_status(tmp_path):
    write(tmp_path, "tool_latency", latency_file())
    server = make_server("127.0.0.1", 0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(base + "/api/status") as response:
            data = json.load(response)
        with urllib.request.urlopen(base + "/") as response:
            page = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
    statuses = {row["key"]: row["status"] for row in data["rows"]}
    assert statuses["tool_latency"] == MET
    assert statuses["sandbox_escape"] == NOT_MEASURED
    assert "/api/status" in page
