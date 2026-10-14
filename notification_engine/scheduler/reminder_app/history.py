"""Print every reminder sent so far and how it was answered.
   usage: python -m reminder_app.history""" 

from reminder_app.config import DATABASE_FILE 
from reminder_app.database import Database 
 
for row in Database(DATABASE_FILE).history(): 
    print(f"{row['id']:>4}  {row['sent_at'][:16]}  {row['response'] or '(waiting)':<10} {row['message']}")