"""What a task looks like, and where the engine gets its tasks from.""" 
import json 
from datetime import datetime 
from typing import Literal 
 
from pydantic import BaseModel 
 
 
class Task(BaseModel): 
    id: str 
    title: str 
    deadline: datetime                                   # always includes the time zone 
    priority: Literal["critical", "high", "normal", "low"] 
    status: Literal["pending", "done"] = "pending" 
 
 
class FakeTaskRepository: 
    """Reads tasks from a JSON file. Hands-on 6 swaps this for the real knowledge 
graph.""" 
 
    def __init__(self, path): 
        self.path = path 
 
    def get_all_tasks(self): 
        with open(self.path, encoding="utf-8") as f: 
            return [Task(**item) for item in json.load(f)] 
 
    def get_pending_tasks(self): 
        return [task for task in self.get_all_tasks() if task.status == "pending"]

    def mark_done(self, task_id): 
        """Mark one task as done and save the file.""" 
        with open(self.path, encoding="utf-8") as f: 
            items = json.load(f) 
        for item in items: 
            if item["id"] == task_id: 
                item["status"] = "done" 
        with open(self.path, "w", encoding="utf-8") as f: 
            json.dump(items, f, indent=2) 