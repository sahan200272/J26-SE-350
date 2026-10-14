"""Start the reminder engine. It checks the tasks every minute until you press Ctrl+C.""" 
from datetime import datetime 
 
from apscheduler.schedulers.blocking import BlockingScheduler 
 
from reminder_app.config import CHECK_EVERY_MINUTES, DATABASE_FILE, TASKS_FILE 
from reminder_app.database import Database
from reminder_app.engine import check_tasks, mark_ignored 
from reminder_app.tasks import FakeTaskRepository 
 
repo = FakeTaskRepository(TASKS_FILE) 
db = Database(DATABASE_FILE) 
 
 
def run_checks(): 
    now = datetime.now().astimezone() 
    for message in check_tasks(repo, db, now): 
        print(f"[{now:%H:%M}] {message}") 
    ignored = mark_ignored(db, now) 
    if ignored: 
        print(f"[{now:%H:%M}] Marked {len(ignored)} unanswered reminder(s) as ignored") 
 
 
print("Engine started. Press Ctrl+C to stop.") 
scheduler = BlockingScheduler() 
scheduler.add_job(run_checks, "interval", minutes=CHECK_EVERY_MINUTES, 
next_run_time=datetime.now()) 
try: 
    scheduler.start() 
except (KeyboardInterrupt, SystemExit): 
    print("Engine stopped.")

