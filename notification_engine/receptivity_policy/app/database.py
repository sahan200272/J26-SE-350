"""The notebook: every reminder sent and every response, saved in SQLite.""" 
import sqlite3 
from datetime import datetime 
 
 
class Database: 
    def __init__(self, path): 
        self.conn = sqlite3.connect(path, check_same_thread=False) 
        self.conn.row_factory = sqlite3.Row          # rows behave like dictionaries 
        self.conn.executescript(""" 
            CREATE TABLE IF NOT EXISTS notifications ( 
                id           INTEGER PRIMARY KEY AUTOINCREMENT, 
                task_id      TEXT NOT NULL, 
                reminder_key TEXT NOT NULL UNIQUE, 
                message      TEXT NOT NULL, 
                sent_at      TEXT NOT NULL 
            ); 
            CREATE TABLE IF NOT EXISTS responses ( 
                notification_id INTEGER PRIMARY KEY REFERENCES notifications(id), 
                response        TEXT NOT NULL, 
                response_at     TEXT NOT NULL 
            ); 
            CREATE TABLE IF NOT EXISTS waiting ( 
                reminder_key TEXT PRIMARY KEY, 
                message      TEXT NOT NULL, 
                until        TEXT NOT NULL, 
                reason       TEXT NOT NULL 
            ); """) 
        self._add_column_if_missing("notifications", "reason", "TEXT") 
        self._add_column_if_missing("notifications", "state", "INTEGER") 
 
    def _add_column_if_missing(self, table, column, kind): 
        """Upgrade a notebook made in Hands-on 4 without losing what's in it.""" 
        columns = [row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")] 
        if column not in columns: 
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}") 
            self.conn.commit() 
 
    def already_sent(self, reminder_key): 
        row = self.conn.execute( 
            "SELECT 1 FROM notifications WHERE reminder_key = ?", (reminder_key,)).fetchone() 
        return row is not None 
 
    def save_notification(self, task_id, reminder_key, message, sent_at, reason=None, state=None): 
        cursor = self.conn.execute( 
            "INSERT INTO notifications (task_id, reminder_key, message, sent_at, reason, state) " 
            "VALUES (?, ?, ?, ?, ?, ?)", 
            (task_id, reminder_key, message, sent_at.isoformat(), reason, state)) 
        self.conn.execute("DELETE FROM waiting WHERE reminder_key = ?", (reminder_key,)) 
        self.conn.commit() 
        return cursor.lastrowid 
 
    def record_response(self, notification_id, response, at): 
        self.conn.execute( 
            "INSERT OR REPLACE INTO responses (notification_id, response, response_at) VALUES (?, ?, ?)", 
            (notification_id, response, at.isoformat())) 
        self.conn.commit() 
 
    def unanswered_sent_before(self, cutoff): 
        rows = self.conn.execute(""" 
            SELECT n.id FROM notifications n 
            LEFT JOIN responses r ON r.notification_id = n.id 
            WHERE r.notification_id IS NULL AND n.sent_at < ?""", (cutoff.isoformat(),)).fetchall() 
        return [row["id"] for row in rows] 
 
    def history(self): 
        return self.conn.execute(""" 
            SELECT n.id, n.task_id, n.message, n.sent_at, n.reason, n.state, r.response 
            FROM notifications n LEFT JOIN responses r ON r.notification_id = n.id 
            ORDER BY n.id""").fetchall() 
 
    # --- New additions --- 
 
    def get_notification(self, notification_id): 
        return self.conn.execute( 
            "SELECT * FROM notifications WHERE id = ?", (notification_id,)).fetchone() 
 
    def recent(self, limit=20): 
        return self.conn.execute(""" 
            SELECT n.id, n.task_id, n.message, n.sent_at, n.reason, r.response 
            FROM notifications n LEFT JOIN responses r ON r.notification_id = n.id 
            ORDER BY n.id DESC LIMIT ?""", (limit,)).fetchall() 
 
    def sent_today(self, now): 
        row = self.conn.execute( 
            "SELECT COUNT(*) AS n FROM notifications WHERE substr(sent_at, 1, 10) = ?", 
            (now.date().isoformat(),)).fetchone() 
        return row["n"] 
 
    def hold(self, reminder_key, message, until, reason): 
        self.conn.execute( 
            "INSERT OR REPLACE INTO waiting (reminder_key, message, until, reason) VALUES (?, ?, ?, ?)", 
            (reminder_key, message, until.isoformat(), reason)) 
        self.conn.commit() 
 
    def waiting_until(self, reminder_key): 
        row = self.conn.execute( 
            "SELECT until FROM waiting WHERE reminder_key = ?", (reminder_key,)).fetchone() 
        return datetime.fromisoformat(row["until"]) if row else None 
 
    def waiting_list(self): 
        return self.conn.execute("SELECT * FROM waiting ORDER BY until").fetchall()





# """The notebook: every reminder sent and every response, saved in SQLite.""" 
# import sqlite3 
 
 
# class Database: 
#     def __init__(self, path): 
#         self.conn = sqlite3.connect(path, check_same_thread=False) 
#         self.conn.row_factory = sqlite3.Row          # rows behave like dictionaries 
#         self.conn.executescript(""" 
#             CREATE TABLE IF NOT EXISTS notifications ( 
#                 id           INTEGER PRIMARY KEY AUTOINCREMENT, 
#                 task_id      TEXT NOT NULL, 
#                 reminder_key TEXT NOT NULL UNIQUE, 
#                 message      TEXT NOT NULL, 
#                 sent_at      TEXT NOT NULL 
#             ); 
#             CREATE TABLE IF NOT EXISTS responses ( 
#                 notification_id INTEGER PRIMARY KEY REFERENCES notifications(id), 
#                 response        TEXT NOT NULL, 
#                 response_at     TEXT NOT NULL 
#             ); 
#         """) 
 
#     def already_sent(self, reminder_key): 
#         row = self.conn.execute( 
#             "SELECT 1 FROM notifications WHERE reminder_key = ?", (reminder_key,)).fetchone() 
#         return row is not None 
 
#     def save_notification(self, task_id, reminder_key, message, sent_at): 
#         cursor = self.conn.execute( 
#             "INSERT INTO notifications (task_id, reminder_key, message, sent_at) VALUES (?, ?, ?, ?)", 
#             (task_id, reminder_key, message, sent_at.isoformat())) 
#         self.conn.commit() 
#         return cursor.lastrowid 
 
#     def record_response(self, notification_id, response, at): 
#         self.conn.execute( 
#             "INSERT OR REPLACE INTO responses (notification_id, response, response_at) VALUES (?, ?, ?)", 
#             (notification_id, response, at.isoformat())) 
#         self.conn.commit() 
 
#     def unanswered_sent_before(self, cutoff): 
#         rows = self.conn.execute(""" 
#             SELECT n.id FROM notifications n 
#             LEFT JOIN responses r ON r.notification_id = n.id 
#             WHERE r.notification_id IS NULL AND n.sent_at < ?""", (cutoff.isoformat(),)).fetchall() 
#         return [row["id"] for row in rows] 
 
#     def history(self): 
#         return self.conn.execute(""" 
#             SELECT n.id, n.task_id, n.message, n.sent_at, r.response 
#             FROM notifications n LEFT JOIN responses r ON r.notification_id = n.id 
#             ORDER BY n.id""").fetchall()