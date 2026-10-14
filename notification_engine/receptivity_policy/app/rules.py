"""The deadline rules: when does a task need a reminder?""" 
from app.config import REMINDER_RULES 
 
 
def reminder_due(task, now): 
    """Return the key of the reminder that is due right now (e.g. 'T001:60m'), or 
None.""" 
    if task.status != "pending" or now >= task.deadline: 
        return None 
    minutes_left = (task.deadline - now).total_seconds() / 60 
    due = [m for m in REMINDER_RULES[task.priority] if minutes_left <= m] 
    if not due: 
        return None 
    return f"{task.id}:{min(due)}m"            # if several are due, only the most urgent 
 
 
def time_left_text(task, now): 
    """Turn the time left into friendly words: '2 days', '5 hours', '45 minutes'.""" 
    minutes = int((task.deadline - now).total_seconds() // 60) 
    if minutes >= 48 * 60: 
        return f"{minutes // (24 * 60)} days" 
    if minutes >= 120: 
        return f"{minutes // 60} hours" 
    if minutes >= 60: 
        return "1 hour" 
    return f"{minutes} minutes"