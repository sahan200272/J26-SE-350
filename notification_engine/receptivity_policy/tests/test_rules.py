from datetime import datetime, timedelta, timezone 
 
from app.rules import reminder_due, time_left_text 
from app.tasks import Task 
 
NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)      # a fixed "now" for every test 
 
 
def task(priority="high", minutes_left=60, status="pending"): 
    return Task(id="T001", title="Submit report", priority=priority, status=status, 
                deadline=NOW + timedelta(minutes=minutes_left)) 
 
 
def test_high_task_exactly_24_hours_away_is_due(): 
    assert reminder_due(task("high", 24 * 60), NOW) == "T001:1440m" 
 
 
def test_high_task_25_hours_away_is_not_due_yet(): 
    assert reminder_due(task("high", 25 * 60), NOW) is None 
 
 
def test_task_past_its_deadline_gets_nothing(): 
    assert reminder_due(task("high", -10), NOW) is None 
 
 
def test_finished_task_gets_nothing(): 
    assert reminder_due(task("high", 30, status="done"), NOW) is None 
 
 
def test_low_task_needs_one_hour_or_less(): 
    assert reminder_due(task("low", 61), NOW) is None 
    assert reminder_due(task("low", 59), NOW) == "T001:60m" 
 
 
def test_when_two_are_due_only_the_most_urgent_is_sent(): 
    # a critical task 50 minutes away is inside both its 24 h and 1 h windows 
    assert reminder_due(task("critical", 50), NOW) == "T001:60m" 
 
 
def test_time_left_in_friendly_words(): 
    assert time_left_text(task(minutes_left=3 * 24 * 60), NOW) == "3 days"
    assert time_left_text(task(minutes_left=5 * 60 + 10), NOW) == "5 hours" 
    assert time_left_text(task(minutes_left=45), NOW) == "45 minutes" 