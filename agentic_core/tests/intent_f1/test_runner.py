"""Tests for scripts/score_intent_f1.py on a tiny hand-made dataset and fake run.

Nothing here reads or scores the 200 eval cases.
"""

import json

from scripts import score_intent_f1 as runner

TRANSCRIPT = (
    "---\nrecording_id: t-{n}\nstarted_at: 2026-01-05T09:00:00+05:30\nspeakers: 2\n---\n\n"
    "[00:00:03] Speaker 1: Hand-made line {n}.\n[00:00:08] Speaker 2: Okay."
)


def _write(tmp_path, records, **run_changes):
    cases = [
        {"id": "T-1", "category": "single_intent", "transcript": TRANSCRIPT.format(n=1),
         "expected": {"notes": [], "events": [
             {"title": "Budget review", "day": "tuesday", "time": "10:00", "attendees": []}]}},
        {"id": "T-2", "category": "noise", "transcript": TRANSCRIPT.format(n=2),
         "expected": {"notes": [], "events": []}},
    ]
    dataset = tmp_path / "cases.json"
    dataset.write_text(json.dumps({"set": "test", "cases": cases}), encoding="utf-8")
    run = {"official": True, "all_run": True, "cases_run": 2, "mode": "grammar",
           "model": "fake", "summary": {"total": {"infra_errors": 0}},
           "dataset_fingerprint": runner.fingerprint(cases), "records": records}
    run.update(run_changes)
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(run), encoding="utf-8")
    return dataset, run_path


GOOD = [
    {"id": "T-1", "status": "ran", "compliant": True, "raw_output": json.dumps(
        {"notes": [], "events": [{"title": "budget review", "day": "tomorrow",
                                  "time": "10:00", "attendees": ["Speaker 1"]}]})},
    {"id": "T-2", "status": "ran", "compliant": True,
     "raw_output": '{"notes": [{"title": "Lunch", "body": "spicy"}], "events": []}'},
]


def test_dev_style_dataset_is_scored_but_never_official(tmp_path, capsys):
    dataset, run_path = _write(tmp_path, GOOD)
    out = tmp_path / "result.json"
    code = runner.main(["--dataset", str(dataset), "--run", str(run_path),
                        "--out", str(out), "--resamples", "50"])
    assert code == 1  # not the eval dataset -> not official
    assert "NOT OFFICIAL" in capsys.readouterr().out
    raw = out.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    result = json.loads(raw)
    assert result["official"] is False
    assert result["scorer"]["llm_calls"] == 0
    total = result["summary"]["total"]
    assert (total["tp"], total["fp"], total["fn"]) == (1, 1, 0)
    assert result["summary"]["by_category"]["noise"]["fp"] == 1
    assert result["records"][1]["extras"] == ["note 'Lunch' (Inbox)"]


def test_broken_run_is_not_measured(tmp_path, capsys):
    dataset, run_path = _write(tmp_path, GOOD[:1], cases_run=1)
    code = runner.main(["--dataset", str(dataset), "--run", str(run_path)])
    assert code == 2
    assert "NOT MEASURED" in capsys.readouterr().out


def test_compliance_disagreement_is_reported(tmp_path, capsys):
    records = [dict(GOOD[0], compliant=False), GOOD[1]]
    dataset, run_path = _write(tmp_path, records)
    runner.main(["--dataset", str(dataset), "--run", str(run_path), "--resamples", "20"])
    assert "disagrees with the run on 1 case" in capsys.readouterr().out
