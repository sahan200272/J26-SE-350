"""Tests for the PP1 panel dashboard status logic (scripts/panel_dashboard)."""

import json
import threading
import urllib.request

import pytest

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


def write(folder, objective_key, data):
    path = folder / BY_KEY[objective_key].evidence
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


# --- missing or broken evidence -------------------------------------------


@pytest.mark.parametrize("key", ["tool_latency", "sandbox_escape", "tpot", "vram"])
def test_missing_file_gives_not_measured(tmp_path, key):
    row = evaluate(BY_KEY[key], tmp_path)
    assert row["status"] == NOT_MEASURED
    assert "not found" in row["reason"]
    assert row["measured"] == "-"


@pytest.mark.parametrize("key", ["schema_compliance", "intent_f1", "sus"])
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
