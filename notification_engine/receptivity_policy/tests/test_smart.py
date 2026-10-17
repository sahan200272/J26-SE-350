from datetime import datetime, timedelta, timezone 
 
from app.agent import QAgent 
from app.database import Database 
from app.engine import check_tasks, mark_ignored 
from app.environment import SEND_NOW, WAIT_30 
from app.smart import learn_from_response 
from app.tasks import Task 
 
NOW = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)      # a Thursday morning 
 
 
class ListRepository: 
    def __init__(self, tasks): 
        self.tasks = tasks 
 
    def get_pending_tasks(self): 
        return [t for t in self.tasks if t.status == "pending"] 
 
 
def one_task(priority="low", minutes_left=50): 
    return ListRepository([Task(id="T001", title="Submit report", priority=priority, deadline=NOW + timedelta(minutes=minutes_left))]) 
 
 
def learner_that_likes(action): 
    agent = QAgent(epsilon=0.0) 
    agent.Q[:, action] = 1.0            # this move scores best in every situation 
    return agent 
 
 
def test_rules_mode_sends_straight_away_with_a_reason(): 
    db = Database(":memory:") 
    assert len(check_tasks(one_task(), db, NOW)) == 1 
    assert "rules mode" in db.history()[0]["reason"] 
 
 
def test_learner_can_hold_a_reminder_for_a_better_moment(): 
    db = Database(":memory:") 
    sent = check_tasks(one_task(), db, NOW, learner_that_likes(WAIT_30)) 
    assert sent == [] 
    assert db.waiting_until("T001:60m") == NOW + timedelta(minutes=30) 
    assert check_tasks(one_task(), db, NOW + timedelta(minutes=10), 
learner_that_likes(WAIT_30)) == [] 
 
 
def test_safety_net_forces_sending_when_the_deadline_is_close(): 
    db = Database(":memory:") 
    agent = learner_that_likes(WAIT_30) 
    check_tasks(one_task(), db, NOW, agent)                          # held for 30 minutes 
    sent = check_tasks(one_task(), db, NOW + timedelta(minutes=31), agent)   # 19 minutes left 
    assert len(sent) == 1 
    assert "too close" in db.history()[0]["reason"] 
    assert db.waiting_list() == []                                   # no longer on hold 
 
 
def test_no_normal_reminder_during_quiet_hours(): 
    db = Database(":memory:") 
    night = NOW.replace(hour=23) 
    repo = ListRepository([Task(id="T002", title="Pay fee", priority="normal", deadline=night + timedelta(hours=2, minutes=30))]) 
    assert check_tasks(repo, db, night, learner_that_likes(SEND_NOW)) == [] 
    assert "quiet hours" in db.waiting_list()[0]["reason"] 
 
 
def test_a_tap_teaches_the_learner(): 
    agent = QAgent(epsilon=0.0) 
    learn_from_response(agent, 279, "done") 
    assert abs(agent.Q[279, SEND_NOW] - 0.2) < 1e-9          # 0 + 0.1 * (2 - 0) 
 
 
def test_being_ignored_also_teaches_the_learner(): 
    db = Database(":memory:") 
    agent = learner_that_likes(SEND_NOW) 
    check_tasks(one_task(), db, NOW, agent) 
    state = db.history()[0]["state"] 
    mark_ignored(db, NOW + timedelta(minutes=31), agent) 
    assert agent.Q[state, SEND_NOW] < 1.0                    # nudged down towards 0 