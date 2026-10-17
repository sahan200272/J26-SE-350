from datetime import datetime, timedelta, timezone 
 
from app.database import Database 
from app.engine import check_tasks, mark_ignored 
from app.tasks import Task 
 
NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc) 
 
 
class ListRepository: 
    """A tiny stand-in repository that holds tasks in a list.""" 
 
    def __init__(self, tasks): 
        self.tasks = tasks 
 
    def get_pending_tasks(self): 
        return [t for t in self.tasks if t.status == "pending"] 
 
 
def make_repo(): 
    return ListRepository([ 
        Task(id="T001", title="Submit report", priority="low", deadline=NOW + timedelta(minutes=50)), 
        Task(id="T002", title="Pay fee", priority="normal", deadline=NOW + timedelta(days=5)), 
    ]) 
 
 
def test_due_reminder_is_sent_once_only(): 
    db = Database(":memory:")                  # a temporary database that lives in memory 
    repo = make_repo() 
    first = check_tasks(repo, db, NOW) 
    second = check_tasks(repo, db, NOW + timedelta(minutes=1)) 
    assert first == ["Reminder: Submit report is due in 50 minutes"] 
    assert second == [] 
 
 
def test_unanswered_reminders_become_ignored_after_30_minutes(): 
    db = Database(":memory:") 
    check_tasks(make_repo(), db, NOW) 
    assert mark_ignored(db, NOW + timedelta(minutes=29)) == [] 
    assert mark_ignored(db, NOW + timedelta(minutes=31)) == [1] 
    assert db.history()[0]["response"] == "ignored" 
 
 
def test_a_response_is_never_overwritten_by_ignored(): 
    db = Database(":memory:") 
    check_tasks(make_repo(), db, NOW) 
    db.record_response(1, "done", NOW + timedelta(minutes=5)) 
    assert mark_ignored(db, NOW + timedelta(minutes=40)) == [] 
    assert db.history()[0]["response"] == "done"