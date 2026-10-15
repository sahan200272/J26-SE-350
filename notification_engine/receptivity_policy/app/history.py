"""Print every reminder sent so far and how it was answered.""" 
from app.config import DATABASE_FILE 
from app.database import Database 
 
for row in Database(DATABASE_FILE).history(): 
    print(f"{row['id']:>4}  {row['sent_at'][:16]}  {row['response'] or '(waiting)':<10} {row['message']}")