from app.environment import SEND_NOW, WAIT_2H, WAIT_30 
from app.shield import DAILY_LIMIT, allowed_actions, is_quiet_hour 
 
PRIORITIES = ["critical", "high", "normal", "low"] 
 
 
def every_situation(): 
    """Every hour, priority, time left (30 min to 48 h) and number sent today.""" 
    for hour in range(24): 
        for priority in PRIORITIES: 
            for minutes_left in range(30, 48 * 60 + 1, 30): 
                for sent_today in range(10): 
                    yield hour, priority, minutes_left, sent_today 
 
 
def test_there_is_always_something_allowed(): 
    for situation in every_situation(): 
        assert len(allowed_actions(*situation)) >= 1 
 
 
def test_never_waits_past_the_deadline(): 
    for hour, priority, minutes_left, sent in every_situation(): 
        allowed = allowed_actions(hour, priority, minutes_left, sent) 
        if WAIT_30 in allowed: 
            assert minutes_left > 30 
        if WAIT_2H in allowed: 
            assert minutes_left > 120 
 
 
def test_urgent_tasks_due_within_the_hour_are_sent_now(): 
    for hour, priority, minutes_left, sent in every_situation(): 
        if priority in ("critical", "high") and minutes_left <= 60: 
            assert allowed_actions(hour, priority, minutes_left, sent) == [SEND_NOW] 
 
 
def test_no_sending_at_night_unless_critical_or_forced(): 
    for hour, priority, minutes_left, sent in every_situation(): 
        if is_quiet_hour(hour) and priority != "critical" and minutes_left > 60: 
            assert SEND_NOW not in allowed_actions(hour, priority, minutes_left, sent)


def test_daily_limit_for_normal_and_low(): 
    for hour, priority, minutes_left, sent in every_situation(): 
        if sent >= DAILY_LIMIT and priority in ("normal", "low") and minutes_left > 30: 
            assert SEND_NOW not in allowed_actions(hour, priority, minutes_left, sent)