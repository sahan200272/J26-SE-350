import json
from os import path 
from app.tasks import FakeTaskRepository 
def test_repository_returns_only_pending_tasks(tmp_path): 
    path = tmp_path / "tasks.json" 
    path.write_text(json.dumps([ 
        {"id": "T1", "title": "A", "deadline": "2026-10-20T17:00+01:00", "priority": "high", "status": "pending"}, 
        {"id": "T2", "title": "B", "deadline": "2026-10-21T17:00+01:00", "priority": "low", "status": "done"}, 
    ])) 
    tasks = FakeTaskRepository(path).get_pending_tasks() 
    assert [t.id for t in tasks] == ["T1"] 
    assert tasks[0].deadline.utcoffset() is not None      # the time zone was kept 