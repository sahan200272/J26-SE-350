import json 
from datetime import datetime, timezone 
 
from fastapi.testclient import TestClient 
 
import app.web as web 
from app.database import Database 
from app.tasks import FakeTaskRepository 
 
 
def setup_app(tmp_path, monkeypatch): 
    """Point the web app at a temporary database and task list, in rules mode.""" 
    tasks = tmp_path / "tasks.json" 
    tasks.write_text(json.dumps([{"id": "T001", "title": "Submit report", "priority": "low", 
            "deadline": "2026-10-15T11:00+00:00", "status": "pending"}])) 
    db_file = str(tmp_path / "test.db") 
    monkeypatch.setattr(web, "DATABASE_FILE", db_file) 
    monkeypatch.setattr(web, "repo", FakeTaskRepository(tasks)) 
    monkeypatch.setattr(web, "agent", None) 
    Database(db_file).save_notification("T001", "T001:60m", "Reminder: Submit report is due in 50 minutes", 
            datetime(2026, 10, 15, 10, 10, tzinfo=timezone.utc), reason="test") 
    return TestClient(web.app), tasks, db_file 
 
 
def test_list_shows_the_reminder(tmp_path, monkeypatch): 
    client, _, _ = setup_app(tmp_path, monkeypatch) 
    data = client.get("/api/notifications").json() 
    assert data["sent"][0]["message"].startswith("Reminder: Submit report") 
    assert data["waiting"] == [] 
 
 
def test_done_is_saved_and_finishes_the_task(tmp_path, monkeypatch): 
    client, tasks, db_file = setup_app(tmp_path, monkeypatch) 
    assert client.post("/api/notifications/1/respond", json={"response": "done"}).status_code == 200 
    assert Database(db_file).history()[0]["response"] == "done" 
    assert json.loads(tasks.read_text())[0]["status"] == "done" 
 
 
def test_bad_answers_are_refused(tmp_path, monkeypatch): 
    client, _, _ = setup_app(tmp_path, monkeypatch) 
    assert client.post("/api/notifications/1/respond", json={"response": "maybe"}).status_code == 422 
    assert client.post("/api/notifications/99/respond", json={"response": "done"}).status_code == 404 