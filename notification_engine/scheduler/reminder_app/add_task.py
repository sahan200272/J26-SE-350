"""Add one task to the pretend task list. 
 
Usage:  python -m reminder_app.add_task "Call supervisor" 62 low 
        (title, minutes until the deadline, priority) 
""" 
import json 
import sys 
from datetime import datetime, timedelta 
 
from reminder_app.config import TASKS_FILE 
from reminder_app.tasks import Task 
 
title, minutes, priority = sys.argv[1], int(sys.argv[2]), sys.argv[3] 
 
with open(TASKS_FILE, encoding="utf-8") as f: 
    tasks = json.load(f) 
 
deadline = datetime.now().astimezone() + timedelta(minutes=minutes) 
new_task = Task(id=f"T{len(tasks) + 1:03d}", title=title, deadline=deadline, 
priority=priority) 
tasks.append(json.loads(new_task.model_dump_json())) 
 
with open(TASKS_FILE, "w", encoding="utf-8") as f: 
    json.dump(tasks, f, indent=2) 
print(f"Added {new_task.id}: {title}, due at {deadline:%H:%M} ({priority})")