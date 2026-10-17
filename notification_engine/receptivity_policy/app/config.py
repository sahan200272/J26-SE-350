"""Settings for the reminder engine, in one place.""" 
# How many minutes before the deadline each priority gets a reminder. 
REMINDER_RULES = { 
    "critical": [24 * 60, 60],     # 24 hours before, and 1 hour before 
    "high": [24 * 60],             # 24 hours before 
    "normal": [3 * 60],            # 3 hours before 
    "low": [60],                   # 1 hour before 
} 
 
CHECK_EVERY_MINUTES = 1            # 1 while testing; 15 for real use 
IGNORE_AFTER_MINUTES = 30          # no response after this long counts as "ignored" 
 
TASKS_FILE = "data/tasks.json" 
DATABASE_FILE = "data/notifications.db" 

# --- Hands-on 5: smart timing --- 
MODE = "smart"                     # "smart" = learner + safety net decide; "rules" = send as soon as due 
START_Q_TABLE = "experiments/results/q_table_everyone.npy"   # the head start from before
LIVE_Q_TABLE = "data/q_table_live.npy"                         # keeps learning from real taps