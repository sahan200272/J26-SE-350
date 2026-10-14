"""Make 200 pretend tasks with deadlines spread over the next two weeks.""" 
import json 
import random 
from datetime import datetime, timedelta 
 
random.seed(42)

TITLES = [ 
    "Submit research proposal", "Send weekly report to supervisor", "Review Nimal's chapter", 
    "Book meeting room for group meeting", "Update GitHub README", "Prepare slides for demo", 
    "Email client about requirements", "Fix login bug", "Read two papers on notifications", 
    "Pay hostel fee", "Reply to lecturer's email", "Finish literature review draft", 
    "Upload assignment to LMS", "Back up project files", "Call the bank", 
    "Prepare questions for viva practice", "Check ethics application status", 
    "Send survey link to classmates", "Renew library books", "Write test cases for rules", 
    "Collect printouts", "Plan team integration day", "Draft thesis introduction", 
    "Order laptop charger", "Submit timesheet", "Share meeting notes with team", 
    "Update risk register", "Prepare budget estimate", "Book doctor's appointment", 
    "Merge teammate's pull request", 
] 
PRIORITIES = ["critical", "high", "normal", "low"] 
WEIGHTS = [10, 25, 45, 20]          # per cent of tasks with each priority 
 
now = datetime.now().astimezone()   # the current time, with your time zone 
tasks = [] 
for i in range(1, 201): 
    minutes_ahead = random.randint(30, 14 * 24 * 60) 
    tasks.append({ 
        "id": f"T{i:03d}", 
        "title": random.choice(TITLES), 
        "deadline": (now + timedelta(minutes=minutes_ahead)).isoformat(timespec="minutes"), 
        "priority": random.choices(PRIORITIES, WEIGHTS)[0], 
        "status": "done" if random.random() < 0.1 else "pending", 
    }) 
 
with open("data/tasks.json", "w", encoding="utf-8") as f: 
    json.dump(tasks, f, indent=2) 
print(f"Saved {len(tasks)} tasks to data/tasks.json")