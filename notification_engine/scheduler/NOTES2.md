## 1. Objective

The objective was to build a working reminder engine around the Proactive Notification and Interaction System. Previously developed the notification receptivity simulator and Q-learning model. Now, I implemented the task management, reminder rules, database, and automatic scheduling parts.
The engine reads tasks from a JSON file, checks whether reminders are due, records reminders in an SQLite database, and periodically checks for new reminders without requiring manual execution.

## 2. Technologies Used

- Python
- Pydantic – validates task data and allowed values.
- APScheduler – runs the reminder check periodically.
- SQLite – stores reminder history and user responses.
- Pytest – tests the task repository, reminder rules, and engine.

## 3. Files Implemented

| File                       | Responsibility                                                              |
|----------------------------|-----------------------------------------------------------------------------|
| `reminder_app/tasks.py`    | Defines the `Task` model and `FakeTaskRepository`.                          |
| `reminder_app/config.py`   | Stores reminder rules, scheduler interval, timeout, and file paths.         |
| `reminder_app/rules.py`    | Determines whether a reminder is due and formats the time remaining.        |
| `reminder_app/database.py` | Stores notifications and responses in SQLite.                               |
| `reminder_app/engine.py`   | Checks tasks, records reminders, and marks unanswered reminders as ignored. |
| `reminder_app/respond.py`  | Records a simulated user response.                                          |
| `reminder_app/history.py`  | Displays notification history and responses.                                |
| `reminder_app/add_task.py` | Adds a new task through the terminal.                                       |
| `data/make_tasks.py`       | Generates 200 sample tasks with different deadlines and priorities.         |
| `main.py`                  | Starts the background scheduler and runs periodic checks.                   |
| `tests/test_tasks.py`      | Tests task retrieval and pending-task filtering.                            |
| `tests/test_rules.py`      | Tests reminder timing and deadline rules.                                   |
| `tests/test_engine.py`     | Tests duplicate prevention, ignored reminders, and response handling.       |

**Note:** My implementation uses the `reminder_app` package name inside `scheduler/`. The imports and commands must consistently use `reminder_app`.

## 4. Task Model and Repository Pattern

I created a `Task` model using Pydantic. Each task contains an ID, title, deadline, priority, and status. The priority is restricted to `critical`, `high`, `normal`, or `low`, while the status is `pending` or `done`.
I also implemented `FakeTaskRepository`, which reads tasks from `data/tasks.json` and returns pending tasks to the engine. This separates task retrieval from reminder processing. Later, the repository can be replaced with one that retrieves tasks from the team's knowledge graph.
The task generator creates 200 sample tasks with time-zone-aware deadlines, different priorities, and a mixture of pending and completed statuses.

## 5. Reminder Rules

The reminder rules are stored in `reminder_app/config.py`, rather than being hard-coded throughout the engine.
The original reminder settings are:
| Priority | Reminder time before deadline |
|----------|-------------------------------|
| Critical | 24 hours and 1 hour           |
| High     | 24 hours                      |
| Normal   | 3 hours                       |
| Low      | 1 hour                        |


## 6. Testing the Rules

The `reminder_due(task, now)` function receives the task and the current time as inputs. It checks the task status, deadline, and priority before deciding whether a reminder is due.
Passing `now` into the function instead of reading the system clock directly makes the rules easier to test with a fixed time.
I added test to verify that a critical task 23 hours away receives the 24-hour reminder:

```python
def test_critical_task_23_hours_away_gets_24_hour_reminder():
    critical_task = task(priority="critical", minutes_left=23 * 60)

    result = reminder_due(critical_task, NOW)

    assert result == "T001:1440m"
```
The expected reminder key is `T001:1440m`, which represents the 24-hour reminder for task `T001`.
The tests cover deadlines that are inside or outside reminder windows, completed tasks, overdue tasks, time-left formatting, and situations where multiple reminder windows apply. When multiple reminders are due at the same time, the rules return the most urgent one.

## 7. Database and Idempotency

I implemented an SQLite database in `data/notifications.db`. It contains two tables:
- `notifications` stores each reminder's ID, task ID, reminder key, message, and send time.
- `responses` stores the response associated with a notification, such as `done`, `opened`, `snoozed`, `dismissed`, or `ignored`.
The `reminder_key` column has a `UNIQUE` constraint. The engine checks whether a reminder has already been recorded before saving it. This helps prevent the same reminder from being recorded or sent repeatedly when the scheduler runs again or the application restarts.
The engine also marks unanswered reminders as `ignored` after 30 minutes. However, it preserves a response that has already been recorded, such as `done`.
The database is excluded from GitHub because it contains changing runtime data and may contain personal reminder information. The database can be recreated locally, so it should not be committed as source code.

## 8. Automatic Scheduling

I used APScheduler's `BlockingScheduler` in `main.py` to run the reminder check automatically.
The engine:
1. Loads tasks from the repository.
2. Gets the current time.
3. Checks each pending task against the reminder rules.
4. Checks whether the reminder has already been recorded.
5. Records and prints new reminders.
6. Marks unanswered notifications as ignored after the configured timeout.
7. Repeats the check at the configured interval.
The interval is set to one minute for testing. It can be changed to 15 minutes for normal operation.

## 9. Testing and Running the Engine

I used the following commands from the `notification_engine/scheduler/` directory with the project's virtual environment activated.
Generate sample tasks:
```powershell
python data/make_tasks.py
```

Run the tests:
```powershell
python -m pytest
```

Start the reminder engine:
```powershell
python main.py
```

In a second terminal, add a task:
```powershell
python -m reminder_app.add_task "Call supervisor" 62 low
```

View the reminder history:
```powershell
python -m reminder_app.history
```

Record a response using the actual notification ID shown in the history:
```powershell
python -m reminder_app.respond 1 done
```

The engine can be stopped with `Ctrl+C`. After restarting it, previously recorded reminders should not be recorded or sent again.

## 10. Important Software Design Ideas

### Separation of concerns
Each file has a specific responsibility. For example, `rules.py` determines reminder timing, `database.py` manages persistent records, and `engine.py` coordinates the process. This makes individual parts easier to understand, test, and modify.

### Repository pattern
The engine retrieves tasks through a repository instead of accessing the JSON file directly. The `FakeTaskRepository` can later be replaced with a knowledge-graph repository without rewriting the whole reminder engine.

### Idempotency
Idempotency means that repeating an operation should not produce duplicate effects. The unique reminder key in SQLite helps prevent duplicate reminder records across periodic checks and application restarts.

### Time-based testing
The reminder rules receive a fixed `now` value during tests. This avoids waiting for real time to pass and makes the test results repeatable.

## 11. Connection to previous implementation

Previously developed a Q-learning agent that learns suitable notification timing from simulated user receptivity, together with a safety net for important reminders.
In the future architecture, the learner and safety net will fit between identifying a task that needs attention and delivering the notification. The learner will help choose an appropriate time, while the safety net will protect urgent reminders from being delayed inappropriately.
This provides the task repository, reminder rules, scheduling framework, and database that later we can extend to integrate personalized timing and the safety net.

## 12. Lessons Learned

- How to validate task data with Pydantic.
- How to separate task retrieval, reminder rules, database operations, and scheduling.
- How to test time-dependent logic using a fixed time.
- How APScheduler executes periodic background checks.
- How SQLite stores reminder history and user responses.
- How unique reminder keys help prevent duplicate records.
- Why persistent runtime data should be excluded from GitHub.
- How the existing Q-learning model can eventually be integrated into a real reminder engine.
