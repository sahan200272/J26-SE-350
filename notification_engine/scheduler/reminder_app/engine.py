"""The reminder engine: check every task, send what's due, never send the same one 
twice.""" 
from datetime import timedelta 
 
from reminder_app.config import IGNORE_AFTER_MINUTES 
from reminder_app.rules import reminder_due, time_left_text 
 
 
def check_tasks(repo, db, now): 
    """Look at every pending task once. Returns the reminders sent this time.""" 
    sent = [] 
    for task in repo.get_pending_tasks(): 
        key = reminder_due(task, now) 
        if key is None or db.already_sent(key): 
            continue 
        message = f"Reminder: {task.title} is due in {time_left_text(task, now)}" 
        db.save_notification(task.id, key, message, now) 
        sent.append(message) 
    return sent 
 
 
def mark_ignored(db, now): 
    """Any reminder with no response after 30 minutes counts as ignored.""" 
    cutoff = now - timedelta(minutes=IGNORE_AFTER_MINUTES) 
    ids = db.unanswered_sent_before(cutoff) 
    for notification_id in ids: 
        db.record_response(notification_id, "ignored", now) 
    return ids