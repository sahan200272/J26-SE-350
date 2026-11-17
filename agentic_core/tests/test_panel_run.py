"""Tests for "Run the pipeline" (panel POST /api/run) and scripts/demo_pipeline.py.

A fake LLM is used, so no Ollama is needed. The MCP servers are the real ones.
"""

import json
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from agentic_core.llm.client import LLMResult
from scripts import demo_pipeline
from scripts.panel_dashboard.server import MAX_TRANSCRIPT_CHARS, make_server
from scripts.panel_dashboard.status import MET

TRANSCRIPT = """---
started_at: 2026-10-12T09:30:00+05:30
---
[00:00:04] Speaker 1: Morning. I will review the login fix after this call.
[00:07:30] Speaker 2: Where should we have lunch?
[00:07:35] Speaker 1: Sounds good.
"""
REPLY = (
    '{"notes":[{"title":"Review login fix","body":"After the call","folder":"Inbox"}],'
    '"events":[{"title":"Demo","day":"friday","time":"10:00","attendees":["Kasun","Speaker 1"]}]}'
)


class FakeClient:
    def __init__(self, text=REPLY, ready=True):
        self.text, self.ready = text, ready
        self.config = SimpleNamespace(model="fake", temperature=0.0, num_ctx=4096, num_predict=512)
        self._client = SimpleNamespace(ps=lambda: SimpleNamespace(models=[]))

    def is_ready(self):
        return self.ready

    def chat(self, user_prompt, system_prompt=None, response_format=None):
        return LLMResult(self.text, 40, 80.0, 3.2)


# --- run_pipeline (shared by the command and the page) ---------------------


def test_pipeline_runs_both_stages_and_blocks_attacks(tmp_path):
    lines = []
    r = demo_pipeline.run_pipeline(TRANSCRIPT, "t.md", tmp_path / "vault", FakeClient(),
                                   attack=True, say=lines.append)
    s = r["summary"]
    assert (s["segments"], s["skipped"], s["llm_calls"], s["valid_first_try"]) == (2, 1, 1, 1)
    assert (s["notes_written"], s["events_created"], s["tool_failures"]) == (1, 1, 0)
    assert (s["attacks_tried"], s["attacks_blocked"]) == (4, 4)
    assert r["ok"] is True
    assert r["recording_date"] == "2026-10-12"
    assert r["segments"][0]["plan"]["events"][0]["start"] == "2026-10-16T10:00:00"  # code did the date
    assert r["segments"][0]["plan"]["events"][0]["attendees"] == ["Kasun"]  # "Speaker 1" dropped
    assert r["segments"][1]["status"] == "skipped"
    assert s["records_written"] == 1  # RP-18: one record note per event
    assert len(list((tmp_path / "vault").rglob("*.md"))) == 2  # the note + the event record
    assert r["log"] == "\n".join(lines)  # the page shows exactly what the terminal shows
    assert "STAGE 1" in r["log"] and "STAGE 2" in r["log"]


def test_invalid_llm_answer_is_shown_not_hidden(tmp_path):
    r = demo_pipeline.run_pipeline(TRANSCRIPT, "t.md", tmp_path / "v", FakeClient("Sure! Here it is."),
                                   say=lambda _l: None)
    assert r["segments"][0]["status"] == "invalid"
    assert r["summary"]["valid_first_try"] == 0 and r["summary"]["notes_written"] == 0
    assert r["ok"] is False


def test_bad_transcript_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        demo_pipeline.run_pipeline("just some text", "t.md", tmp_path / "v", FakeClient(),
                                   say=lambda _l: None)


def test_command_line_still_works(tmp_path, capfd):
    path = tmp_path / "t.md"
    path.write_text(TRANSCRIPT, encoding="utf-8")
    code = demo_pipeline.main([str(path), "--vault", str(tmp_path / "v"), "--attack"], client=FakeClient())
    assert code == 0
    assert "All steps OK." in capfd.readouterr().out


# --- the page's /api/run ------------------------------------------------------


@pytest.fixture()
def panel(tmp_path):
    clients = {"next": FakeClient()}
    server = make_server("127.0.0.1", 0, tmp_path / "eval", tmp_path / "vault", lambda: clients["next"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(base + "/api/run", data=data,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def get(path):
        with urllib.request.urlopen(base + path) as response:
            return json.load(response)

    yield SimpleNamespace(post=post, get=get, clients=clients, vault=tmp_path / "vault")
    server.shutdown()
    server.server_close()


def test_pasted_transcript_runs_and_writes_into_a_run_folder(panel):
    code, r = panel.post({"transcript": TRANSCRIPT, "attack": True})
    assert code == 200
    assert r["summary"]["attacks_blocked"] == 4 and r["ok"] is True
    assert r["vault"].startswith(str(panel.vault)) and "run_" in r["vault"]
    assert len(list(panel.vault.rglob("*.md"))) == 2  # the note + the event record (RP-18)


def test_run_never_changes_the_target_rows(panel):
    panel.post({"transcript": TRANSCRIPT, "attack": True})
    rows = panel.get("/api/status")["rows"]
    assert len(rows) == 7 and all(row["status"] != MET for row in rows)


def test_sample_button_gets_the_sample_transcript(panel):
    data = panel.get("/api/sample")
    assert data["name"] == "sample_standup.md" and "Speaker 1" in data["text"]


def test_date_box_is_used_when_the_header_has_no_date(panel):
    no_header = "[00:00:04] Speaker 1: I will book the room for Friday at ten o'clock.\n"
    code, r = panel.post({"transcript": no_header, "date": "2026-10-19"})
    assert code == 200 and r["recording_date"] == "2026-10-19"
    code, r = panel.post({"transcript": no_header})
    assert code == 400 and "date" in r["error"]


@pytest.mark.parametrize("body, expected", [
    ({"transcript": ""}, 400),
    ({"transcript": "not a transcript"}, 400),
    ({"nothing": True}, 400),
    (b"{ not json", 400),
    ({"transcript": "x" * (MAX_TRANSCRIPT_CHARS + 1)}, 413),
])
def test_bad_requests_are_refused_with_a_reason(panel, body, expected):
    code, r = panel.post(body)
    assert code == expected and r["error"]
    assert not panel.vault.exists() or not list(panel.vault.rglob("*.md"))


def test_ollama_not_running_is_explained(panel):
    panel.clients["next"] = FakeClient(ready=False)
    code, r = panel.post({"transcript": TRANSCRIPT})
    assert code == 503 and "Ollama" in r["error"]
