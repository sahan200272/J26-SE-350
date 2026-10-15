"""The reminder engine: check every task, send what's due, never send the same one 
twice.""" 
from datetime import timedelta 
 
from app.config import IGNORE_AFTER_MINUTES 
from app.environment import SEND_NOW 
from app.rules import reminder_due, time_left_text 
from app.smart import WAIT_MINUTES, decide, learn_from_response 
 
 
def check_tasks(repo, db, now, agent=None): 
    """Look at every pending task once. Returns the reminders sent this time. 
 
    With no agent, a due reminder is sent straight away (rules mode). 
    With an agent, the learner and safety net decide whether to send now or hold it. 
    """ 
    sent = [] 
    for task in repo.get_pending_tasks(): 
        key = reminder_due(task, now) 
        if key is None or db.already_sent(key): 
            continue 
        message = f"Reminder: {task.title} is due in {time_left_text(task, now)}" 
 
        if agent is None: 
            db.save_notification(task.id, key, message, now, reason="Sent now: the reminder window opened (rules mode)") 
            sent.append(message) 
            continue 
 
        held_until = db.waiting_until(key) 
        if held_until is not None and now < held_until: 
            continue                                   # still holding: decide again later 
        state, action, reason = decide(agent, task, now, db.sent_today(now)) 
        if action == SEND_NOW: 
            db.save_notification(task.id, key, message, now, reason=reason, state=state) 
            sent.append(message) 
        else: 
            db.hold(key, message, now + timedelta(minutes=WAIT_MINUTES[action]), reason) 
    return sent 
 
 
def mark_ignored(db, now, agent=None): 
    """Any reminder with no response after 30 minutes counts as ignored (and teaches the learner).""" 
    cutoff = now - timedelta(minutes=IGNORE_AFTER_MINUTES) 
    ids = db.unanswered_sent_before(cutoff) 
    for notification_id in ids: 
        db.record_response(notification_id, "ignored", now) 
        row = db.get_notification(notification_id) 
        if agent is not None and row["state"] is not None: 
            learn_from_response(agent, row["state"], "ignored") 
    return ids



# """The reminder engine: check every task, send what's due, never send the same one 
# twice."""
# from datetime import timedelta 
 
# from app.config import IGNORE_AFTER_MINUTES 
# from app.rules import reminder_due, time_left_text 
 
 
# def check_tasks(repo, db, now): 
#     """Look at every pending task once. Returns the reminders sent this time.""" 
#     sent = [] 
#     for task in repo.get_pending_tasks(): 
#         key = reminder_due(task, now) 
#         if key is None or db.already_sent(key): 
#             continue 
#         message = f"Reminder: {task.title} is due in {time_left_text(task, now)}" 
#         db.save_notification(task.id, key, message, now) 
#         sent.append(message) 
#     return sent 
 
 
# def mark_ignored(db, now): 
#     """Any reminder with no response after 30 minutes counts as ignored.""" 
#     cutoff = now - timedelta(minutes=IGNORE_AFTER_MINUTES) 
#     ids = db.unanswered_sent_before(cutoff) 
#     for notification_id in ids: 
#         db.record_response(notification_id, "ignored", now) 
#     return ids 