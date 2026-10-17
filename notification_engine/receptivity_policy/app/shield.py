"""The safety net: rules that always win over the learner.""" 
from app.environment import SEND_NOW, WAIT_2H, WAIT_30 
 
QUIET_START = 22     # no reminders from 10 PM ... 
QUIET_END = 7        # ... until 7 AM 
DAILY_LIMIT = 6      # at most 6 normal or low reminders a day 
 
 
def is_quiet_hour(hour): 
    return hour >= QUIET_START or hour < QUIET_END 
 
 
def allowed_actions(hour, priority, minutes_left, sent_today): 
    """Return the moves the learner is allowed to choose from right now.""" 
    # Rule 1: never wait past the deadline. 
    moves = [SEND_NOW] 
    if minutes_left > 30: 
        moves.append(WAIT_30) 
    if minutes_left > 120: 
        moves.append(WAIT_2H) 
    can_wait = len(moves) > 1 
 
    # Rule 2: urgent and due within the hour: send now, no discussion. 
    if priority in ("critical", "high") and minutes_left <= 60: 
        return [SEND_NOW] 
 
    # Rule 3: quiet hours. No sending at night unless it's critical. 
    if can_wait and is_quiet_hour(hour) and priority != "critical": 
        moves.remove(SEND_NOW) 
 
    # Rule 4: daily limit. After 6 reminders, normal and low ones wait for tomorrow. 
    if can_wait and SEND_NOW in moves and sent_today >= DAILY_LIMIT and priority in ("normal", "low"): 
        moves.remove(SEND_NOW) 
 
    return moves 
 
 
def allowed_for(env): 
    """The same rules, reading the situation straight from the practice world.""" 
    return allowed_actions(env.hour(), env.priority, env.minutes_left, env.sent_today)