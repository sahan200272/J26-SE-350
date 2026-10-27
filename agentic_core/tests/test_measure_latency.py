"""Tests for the latency measuring script (RP-16, section 4b)."""

import json

import pytest

from scripts.measure_tool_latency import main, percentile, summarise


def test_percentile_uses_nearest_rank():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 50) == 30.0
    assert percentile(values, 95) == 50.0
    assert percentile([7.0], 95) == 7.0


def test_summarise():
    result = summarise([3.0, 1.0, 2.0])
    assert result == {"calls": 3, "median_ms": 2.0, "p95_ms": 3.0, "max_ms": 3.0}


def test_bad_arguments_are_refused():
    with pytest.raises(SystemExit):
        main(["--plans", "0"])


def test_small_real_run_writes_a_valid_json_result(tmp_path, capfd):
    out = tmp_path / "latency.json"
    code = main(["--plans", "3", "--warmup", "1", "--out", str(out)])
    text = capfd.readouterr().out

    assert code == 0
    assert "real Google calls NOT measured" in text
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["valid"] is True and data["failures"] == 0
    assert data["summary"]["write_note"]["calls"] == 3
    assert data["summary"]["create_event"]["calls"] == 3
    assert data["connect_ms"] > 0