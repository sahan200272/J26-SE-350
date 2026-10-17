"""Pretend to tap a button on a reminder, until the web page exists (Hands-on 5). 
 
Usage:  python -m app.respond 3 done 
""" 
import sys 
from datetime import datetime 
 
from app.config import DATABASE_FILE 
from app.database import Database 
 
ALLOWED = {"opened", "done", "snoozed", "dismissed"} 
 
notification_id, response = int(sys.argv[1]), sys.argv[2] 
if response not in ALLOWED: 
    sys.exit(f"Response must be one of: {', '.join(sorted(ALLOWED))}") 
Database(DATABASE_FILE).record_response(notification_id, response, 
datetime.now().astimezone()) 
print(f"Saved: reminder {notification_id} -> {response}") 
