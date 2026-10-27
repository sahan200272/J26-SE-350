"""Tests for the schema-compliance harness and runner (NFR-04). A fake LLM is used, never Ollama."""

import json

import pytest

from agentic_core.decoding.plan_schema import DraftPlan
from agentic_core.llm.client import LLMResult
from agentic_core.llm.config import load_config
from agentic_core.tests.schema_compliance import frozen_setup
from agentic_core.tests.schema_compliance.cases import DEV_PATH, fingerprint, load_cases
from agentic_core.tests.schema_compliance.harness import (
    RecordingClient,
    check_output,
    run_case,
    setup_hashes,
    summarize,
    wilson_interval,
)
from scripts import run_schema_compliance as runner

GOOD = '{"notes": [], "events": [{"title": "Demo", "day": "friday", "time": "11:00", "attendees": []}]}'
BAD_TIME = '{"notes": [], "events": [{"title": "Demo", "day": "friday", "time": "3 pm", "attendees": []}]}'
CUT = '{"notes": [{"title": "A long note", "body": "and then the model kept writing and'
EMPTY = '{"notes": [], "events": []}'


class FakeClient:
    """Stands in for LLMClient. `answer` is a string, an exception, or a function of the call number."""

    def __init__(self, answer=GOOD, tokens=20):
        self.config = load_config()
        self.answer = answer
        self.tokens = tokens
        self.formats = []

    def chat(self, user_prompt, system_prompt=None, response_format=None):
        self.formats.append(response_format)
        answer = self.answer(len(self.formats)) if callable(self.answer) else self.answer
        if isinstance(answer, BaseException):
            raise answer
        tokens = self.tokens(answer) if callable(self.tokens) else self.tokens
        return LLMResult(text=answer, tokens_out=tokens, tpot_ms=80.0, total_s=1.5)


DEV = load_cases(DEV_PATH)
CASE = DEV[0]


# ---------- check_output ----------

def test_good_answer_is_json_and_schema_valid():
    assert check_output(GOOD) == (True, True, [], [])


def test_broken_json_fails_both_checks():
    json_ok, schema_ok, types, _ = check_output("Sure! Here is your plan: {")
    assert (json_ok, schema_ok) == (False, False)
    assert types == ["json_invalid"]


def test_valid_json_with_bad_time_fails_only_the_schema():
    json_ok, schema_ok, types, details = check_output(BAD_TIME)
    assert (json_ok, schema_ok) == (True, False)
    assert types == ["value_error"]
    assert details == ["events.0.time: value_error"]


def test_all_errors_are_reported_not_only_the_first():
    text = '{"notes": [{"title": "", "body": "x", "folder": "Secret"}], "events": []}'
    _, _, types, details = check_output(text)
    assert len(details) == 2 and len(types) == 2


# ---------- RecordingClient ----------

def test_grammar_mode_sends_the_draft_schema():
    fake = FakeClient()
    run_case(CASE, RecordingClient(fake, "grammar"))
    assert fake.formats == [DraftPlan.model_json_schema()]


def test_baseline_mode_sends_no_grammar():
    fake = FakeClient()
    recorder = RecordingClient(fake, "baseline")
    run_case(CASE, recorder)
    assert fake.formats == [None] and recorder.grammar_sent == [False]


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        RecordingClient(FakeClient(), "loose")


# ---------- run_case ----------

def test_compliant_case_is_recorded_with_raw_output():
    record = run_case(CASE, RecordingClient(FakeClient(GOOD), "grammar"))
    assert record["status"] == "ran" and record["compliant"] is True
    assert record["raw_output"] == GOOD and record["extractor_agrees"] is True
    assert record["cut_off"] is False


def test_bad_time_case_is_not_compliant_and_extractor_agrees():
    record = run_case(CASE, RecordingClient(FakeClient(BAD_TIME), "grammar"))
    assert record["compliant"] is False and record["json_valid"] is True
    assert record["extractor_agrees"] is True and record["extractor_error"]


def test_answer_cut_at_num_predict_is_flagged():
    fake = FakeClient(CUT, tokens=load_config().num_predict)
    record = run_case(CASE, RecordingClient(fake, "grammar"))
    assert record["cut_off"] is True and record["json_valid"] is False and record["compliant"] is False


def test_ollama_exception_becomes_infra_error_not_a_model_failure():
    record = run_case(CASE, RecordingClient(FakeClient(ConnectionError("refused")), "grammar"))
    assert record["status"] == "infra_error" and "ConnectionError" in record["infra_error"]
    assert "compliant" not in record


# ---------- numbers ----------

def test_wilson_interval_known_values():
    low, high = wilson_interval(200, 200)
    assert low == pytest.approx(0.98115, abs=1e-4) and high == pytest.approx(1.0)
    low, high = wilson_interval(196, 200)
    assert low == pytest.approx(0.9497, abs=1e-3) and high == pytest.approx(0.9922, abs=1e-3)
    assert wilson_interval(0, 0) is None


def test_summary_counts_per_category_and_ignores_infra_errors_in_the_rate():
    records = [
        {"id": "a", "category": "noise", "status": "ran", "compliant": True, "json_valid": True,
         "schema_valid": True, "cut_off": False, "extractor_agrees": True, "error_types": [],
         "tokens_out": 10, "llm_total_s": 1.0},
        {"id": "b", "category": "noise", "status": "ran", "compliant": False, "json_valid": False,
         "schema_valid": False, "cut_off": True, "extractor_agrees": True, "error_types": ["json_invalid"],
         "tokens_out": 512, "llm_total_s": 40.0},
        {"id": "c", "category": "ambiguous", "status": "infra_error", "infra_error": "X"},
    ]
    summary = summarize(records)
    assert summary["total"]["cases_run"] == 2 and summary["total"]["infra_errors"] == 1
    assert summary["total"]["rate"] == 0.5 and summary["total"]["cut_off"] == 1
    assert summary["by_category"]["noise"]["error_type_counts"] == {"json_invalid": 1}
    assert summary["by_category"]["ambiguous"]["rate"] is None


# ---------- the script ----------

@pytest.fixture
def no_probes(monkeypatch):
    """Keep the tests away from the real 'ollama ps' and 'nvidia-smi'."""
    monkeypatch.setattr(runner, "model_placement", lambda model: {"placement": "test", "line": "test"})
    monkeypatch.setattr(runner, "machine_info", lambda: {"gpu": "test"})


def small_dataset(tmp_path, count=3):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": DEV[:count]}), encoding="utf-8")
    return path


def test_custom_dataset_run_writes_a_not_official_result(tmp_path, no_probes):
    out = tmp_path / "r.json"
    code = runner.main(["--dataset", str(small_dataset(tmp_path)), "--out", str(out)], client=FakeClient(EMPTY))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert data["official"] is False and data["all_run"] is True and data["cases_run"] == 3
    assert data["summary"]["total"]["rate"] == 1.0 and len(data["records"]) == 3


def test_rate_below_target_gives_exit_code_1(tmp_path, no_probes):
    answers = lambda n: GOOD if n % 2 else BAD_TIME
    code = runner.main(["--dataset", str(small_dataset(tmp_path, 4))], client=FakeClient(answers))
    assert code == 1


def test_baseline_mode_has_no_target(tmp_path, no_probes):
    out = tmp_path / "b.json"
    code = runner.main(["--dataset", str(small_dataset(tmp_path)), "--mode", "baseline", "--out", str(out)],
                       client=FakeClient(BAD_TIME))
    assert code == 0 and json.loads(out.read_text(encoding="utf-8"))["mode"] == "baseline"


def test_infra_error_makes_the_run_incomplete(tmp_path, no_probes):
    out = tmp_path / "r.json"
    answers = lambda n: TimeoutError("slow") if n == 2 else EMPTY
    code = runner.main(["--dataset", str(small_dataset(tmp_path)), "--out", str(out)], client=FakeClient(answers))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1 and data["all_run"] is False and data["summary"]["total"]["infra_errors"] == 1


def test_ctrl_c_writes_a_partial_file_marked_incomplete(tmp_path, no_probes):
    out = tmp_path / "r.json"
    answers = lambda n: KeyboardInterrupt() if n == 2 else EMPTY
    code = runner.main(["--dataset", str(small_dataset(tmp_path)), "--out", str(out)], client=FakeClient(answers))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1 and data["interrupted"] is True and data["all_run"] is False and data["cases_run"] == 1


def test_changed_eval_dataset_stops_with_exit_code_2(tmp_path, monkeypatch, no_probes):
    monkeypatch.setattr(runner, "EVAL_PATH", small_dataset(tmp_path))
    out = tmp_path / "r.json"
    fake = FakeClient()
    assert runner.main(["--dataset", str(runner.EVAL_PATH), "--out", str(out)], client=fake) == 2
    assert not out.exists() and fake.formats == []


def test_frozen_eval_with_frozen_setup_is_official(tmp_path, monkeypatch, no_probes):
    path = small_dataset(tmp_path)
    monkeypatch.setattr(runner, "EVAL_PATH", path)
    monkeypatch.setattr(runner, "FROZEN_FINGERPRINT", fingerprint(load_cases(path)))
    monkeypatch.setattr(frozen_setup, "FROZEN_SETUP_HASHES", setup_hashes())
    out = tmp_path / "r.json"
    assert runner.main(["--dataset", str(path), "--out", str(out)], client=FakeClient(EMPTY)) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["official"] is True


def test_setup_not_frozen_yet_means_not_official(tmp_path, monkeypatch, no_probes):
    path = small_dataset(tmp_path)
    monkeypatch.setattr(runner, "EVAL_PATH", path)
    monkeypatch.setattr(runner, "FROZEN_FINGERPRINT", fingerprint(load_cases(path)))
    monkeypatch.setattr(frozen_setup, "FROZEN_SETUP_HASHES", None)
    out = tmp_path / "r.json"
    runner.main(["--dataset", str(path), "--out", str(out)], client=FakeClient(EMPTY))
    assert json.loads(out.read_text(encoding="utf-8"))["official"] is False


def test_changed_setup_stops_with_exit_code_2(tmp_path, monkeypatch, no_probes):
    path = small_dataset(tmp_path)
    monkeypatch.setattr(runner, "EVAL_PATH", path)
    monkeypatch.setattr(runner, "FROZEN_FINGERPRINT", fingerprint(load_cases(path)))
    changed = dict(setup_hashes(), system_prompt="0" * 64)
    monkeypatch.setattr(frozen_setup, "FROZEN_SETUP_HASHES", changed)
    fake = FakeClient()
    assert runner.main(["--dataset", str(path)], client=fake) == 2 and fake.formats == []


def test_limit_is_never_official(tmp_path, monkeypatch, no_probes):
    path = small_dataset(tmp_path)
    monkeypatch.setattr(runner, "EVAL_PATH", path)
    monkeypatch.setattr(runner, "FROZEN_FINGERPRINT", fingerprint(load_cases(path)))
    monkeypatch.setattr(frozen_setup, "FROZEN_SETUP_HASHES", setup_hashes())
    out = tmp_path / "r.json"
    runner.main(["--dataset", str(path), "--limit", "2", "--out", str(out)], client=FakeClient(EMPTY))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["official"] is False and data["cases"] == 2
