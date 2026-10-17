"""The web app: shows reminders, records taps, and runs the reminder engine in the 
background. 
Start it with:  python -m app.web 
""" 
import shutil 
import threading 
from contextlib import asynccontextmanager 
from datetime import datetime 
from pathlib import Path 
from typing import Literal 
 
import uvicorn 
from apscheduler.schedulers.background import BackgroundScheduler 
from fastapi import FastAPI, HTTPException 
from fastapi.responses import FileResponse 
from pydantic import BaseModel 
 
from app.agent import QAgent 
from app.config import (CHECK_EVERY_MINUTES, DATABASE_FILE, LIVE_Q_TABLE, MODE, 
                        START_Q_TABLE, TASKS_FILE) 
from app.database import Database 
from app.engine import check_tasks, mark_ignored 
from app.smart import learn_from_response 
from app.tasks import FakeTaskRepository 
 
 
def load_agent(): 
    """Load the live learner. The first time, copy the 'everyone' model as its head start.""" 
    if not Path(LIVE_Q_TABLE).exists(): 
        shutil.copy(START_Q_TABLE, LIVE_Q_TABLE) 
    agent = QAgent(epsilon=0.0)          # with real people: no random tries 
    agent.load(LIVE_Q_TABLE) 
    return agent 
 
 
repo = FakeTaskRepository(TASKS_FILE) 
agent = load_agent() if MODE == "smart" else None 
lock = threading.Lock()                  # one change to the learner at a time 
 
 
def run_checks(): 
    db = Database(DATABASE_FILE) 
    now = datetime.now().astimezone() 
    with lock: 
        for message in check_tasks(repo, db, now, agent): 
            print(f"[{now:%H:%M}] {message}") 
        mark_ignored(db, now, agent) 
        if agent is not None: 
            agent.save(LIVE_Q_TABLE) 
 
 
@asynccontextmanager 
async def lifespan(app): 
    scheduler = BackgroundScheduler() 
    scheduler.add_job(run_checks, "interval", minutes=CHECK_EVERY_MINUTES, 
next_run_time=datetime.now()) 
    scheduler.start() 
    print(f"Engine running in {MODE} mode") 
    yield 
    scheduler.shutdown() 
 
 
app = FastAPI(lifespan=lifespan) 
 
 
class Answer(BaseModel): 
    response: Literal["done", "snoozed", "dismissed"] 
 
 
@app.get("/") 
def home(): 
    return FileResponse("app/static/index.html") 
 
 
@app.get("/api/notifications") 
def list_notifications(): 
    db = Database(DATABASE_FILE) 
    return {"mode": MODE, 
            "sent": [dict(row) for row in db.recent(20)], 
            "waiting": [dict(row) for row in db.waiting_list()]} 
 
 
@app.post("/api/notifications/{notification_id}/respond") 
def respond(notification_id: int, answer: Answer): 
    db = Database(DATABASE_FILE) 
    row = db.get_notification(notification_id) 
    if row is None: 
        raise HTTPException(status_code=404, detail="No such reminder") 
    db.record_response(notification_id, answer.response, datetime.now().astimezone()) 
    if answer.response == "done": 
        repo.mark_done(row["task_id"]) 
    if agent is not None and row["state"] is not None: 
        with lock: 
            learn_from_response(agent, row["state"], answer.response) 
            agent.save(LIVE_Q_TABLE) 
    return {"ok": True} 
 
 
if __name__ == "__main__": 
    uvicorn.run(app, host="0.0.0.0", port=8000)