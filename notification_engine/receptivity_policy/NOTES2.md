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
| `app/tasks.py`             | Defines the `Task` model and `FakeTaskRepository`.                          |
| `app/config.py`            | Stores reminder rules, scheduler interval, timeout, and file paths.         |
| `app/rules.py`             | Determines whether a reminder is due and formats the time remaining.        |
| `app/database.py`          | Stores notifications and responses in SQLite.                               |
| `app/engine.py`            | Checks tasks, records reminders, and marks unanswered reminders as ignored. |
| `app/respond.py`           | Records a simulated user response.                                          |
| `app/history.py`           | Displays notification history and responses.                                |
| `app/add_task.py`          | Adds a new task through the terminal.                                       |
| `data/make_tasks.py`       | Generates 200 sample tasks with different deadlines and priorities.         |
| `main.py`                  | Starts the background scheduler and runs periodic checks.                   |
| `tests/test_tasks.py`      | Tests task retrieval and pending-task filtering.                            |
| `tests/test_rules.py`      | Tests reminder timing and deadline rules.                                   |
| `tests/test_engine.py`     | Tests duplicate prevention, ignored reminders, and response handling.       |


## 4. Task Model and Repository Pattern

I created a `Task` model using Pydantic. Each task contains an ID, title, deadline, priority, and status. The priority is restricted to `critical`, `high`, `normal`, or `low`, while the status is `pending` or `done`.
I also implemented `FakeTaskRepository`, which reads tasks from `data/tasks.json` and returns pending tasks to the engine. This separates task retrieval from reminder processing. Later, the repository can be replaced with one that retrieves tasks from the team's knowledge graph.
The task generator creates 200 sample tasks with time-zone-aware deadlines, different priorities, and a mixture of pending and completed statuses.

## 5. Reminder Rules

The reminder rules are stored in `app/config.py`, rather than being hard-coded throughout the engine.
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

I used the following commands from the `notification_engine/receptivity_policy/` directory with the project's virtual environment activated.
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


# Smart Reminder Timing and Web Interface

## 1. Objective

The objective was to integrate the previously developed Q-learning model and safety shield into the Proactive Notification and Interaction System and build a web interface for interacting with reminders.
Previously, I developed a notification receptivity simulator, a Q-learning agent, a safety shield, and a reminder engine. In this implementation, I extended the reminder engine to make intelligent timing decisions based on the trained model instead of always sending reminders as soon as they become due.
The system evaluates whether to send a reminder immediately or hold it for 30 minutes or 2 hours. The safety shield checks the available actions to prevent important reminders from being delayed beyond safe limits or normal reminders from being sent during quiet hours.
I also developed a web interface that displays sent and waiting reminders and allows users to respond using Done, Snooze, and Dismiss buttons. The system learns from real user responses and saves the updated model for future use.

## 2. Technologies Used

- **Python** – Implements the reminder engine, learning logic, and web server.
- **Q-learning** – Selects suitable reminder timing based on the current situation.
- **NumPy** – Stores and loads the trained and live Q-tables.
- **FastAPI** – Provides REST API endpoints for retrieving reminders and recording user responses.
- **Uvicorn** – Runs the FastAPI web application.
- **APScheduler** – Executes reminder checks automatically in the background.
- **SQLite** – Stores reminder history, user responses, and waiting reminders.
- **Pydantic** – Validates incoming response data.
- **HTML, CSS, and JavaScript** – Build the responsive web interface.
- **httpx** – Supports HTTP-based testing.
- **Pytest** – Tests smart timing, reminder processing, and API endpoints.
- **Threading locks** – Prevent simultaneous updates to the learning model.

## 3. Files Implemented

| File                                        | Responsibility                                                                                       |
|---------------------------------------------|------------------------------------------------------------------------------------------------------|
| `app/config.py`                             | Defines the operating mode and paths for the starting and live Q-tables.                             |
| `app/database.py`                           | Stores notifications and responses, maintains the waiting list, and supports database migration.     |
| `app/smart.py`                              | Integrates the Q-learning agent and safety shield to make timing decisions and learn from responses. |
| `app/engine.py`                             | Checks pending tasks, sends or holds reminders, and learns from ignored notifications.               |
| `app/tasks.py`                              | Provides the task model and repository, including functionality to mark completed tasks.             |
| `app/web.py`                                | Runs the FastAPI application, background scheduler, API endpoints, and learning process.             |
| `app/static/index.html`                     | Displays reminders and provides Done, Snooze, and Dismiss buttons.                                   |
| `tests/test_smart.py`                       | Tests smart timing, safety restrictions, holding reminders, and learning from responses.             |
| `tests/test_web.py`                         | Tests notification retrieval, response handling, task completion, and invalid requests.              |
| `data/tasks.json`                           | Stores sample tasks and their statuses.                                                              |
| `data/notifications.db`                     | Stores reminder history, responses, and waiting reminders.                                           |
| `data/q_table_live.npy`                     | Stores the personalized Q-table that is updated through real user feedback.                          |
| `experiments/results/q_table_everyone.npy`  | Provides the trained initial model for new users.                                                    |

The existing files from the earlier implementation, including the state encoder, Q-learning agent, environment, safety shield, and reminder rules, are reused rather than rewritten.

## 4. Smart Reminder Timing

I implemented the smart timing logic in `app/smart.py`. It connects the trained Q-learning model with the existing reminder engine and safety shield.

When a reminder becomes due, the system follows these steps:

1. Calculates the time remaining until the task deadline.
2. Encodes the current situation into a state number using `encode_state()`.
3. Calls `allowed_actions()` to identify the actions permitted by the safety shield.
4. Uses `agent.choose()` to select an action from the permitted actions.
5. Sends the reminder immediately or holds it for a specified period.
6. Generates a short explanation describing why the reminder was sent or delayed.

The available actions are:

| Action     | Behaviour                          |
|------------|------------------------------------|
| `SEND_NOW` | Sends the reminder immediately.    |
| `WAIT_30`  | Holds the reminder for 30 minutes. |
| `WAIT_2H`  | Holds the reminder for 120 minutes.|

The selected waiting period is stored in the SQLite waiting table. When the engine checks the task again, it evaluates the reminder using the current time and the updated time remaining.

### Safety shield

The safety shield is implemented in `app/shield.py` and reused by the smart timing component. It restricts the learner's choices according to the existing safety rules.
For example, a normal reminder cannot be sent during quiet hours. If waiting is no longer safe because the deadline is approaching, the shield can prevent the learner from choosing a waiting action.
This ensures that the learning model does not have complete freedom to make unsafe timing decisions. Safety restrictions take priority over the learner's preference.

### Explainable AI

Each sent reminder contains a `reason` field explaining why it was delivered at that time.

Examples include:

- `Sent now: the deadline is too close to wait`
- `Sent now: your learner rated sending this morning better than waiting`
- `Sent now: the reminder window opened (rules mode)`

Held reminders also include an explanation, such as a likely better moment or a quiet-hours restriction.
These explanations help users understand the system's decisions rather than receiving reminders without knowing why they were sent.

## 5. Upgrading the SQLite Database

I extended `app/database.py` to support smart reminder processing and real user interactions.

The database contains three tables.

| Table           | Purpose                                                                                      |
|-----------------|----------------------------------------------------------------------------------------------|
| `notifications` | Stores the task ID, reminder key, message, sending time, explanation, and encoded state.     |
| `responses`     | Stores the user's response and the time it was recorded.                                     |
| `waiting`       | Stores reminders that are temporarily held, including their next evaluation time and reason. |

### New database functionality

I implemented additional methods to retrieve individual notifications, retrieve recent notifications, count reminders sent on the current date, store held reminders, and retrieve the waiting list.

The `save_notification()` method also removes a reminder from the waiting list when it is finally sent.

### Database migration

The existing notification database was created before the new `reason` and `state` columns were introduced. I added `_add_column_if_missing()` to check the existing table structure and add missing columns when necessary.
This allows the application to upgrade an existing database without deleting its previous reminder records.

### Duplicate prevention

The `reminder_key` column has a `UNIQUE` constraint. The engine checks whether a reminder has already been sent before processing it.
This helps prevent duplicate reminders when the background scheduler performs repeated checks or when the application restarts.

## 6. Connecting the Learner to the Reminder Engine

I upgraded `app/engine.py` to integrate smart timing while preserving the original rules-based behaviour.

The engine now supports two operating modes.

| Mode    | Behaviour                                                                                 |
|---------|-------------------------------------------------------------------------------------------|
| `smart` | Uses the Q-learning agent and safety shield to decide whether to send or hold a reminder. |
| `rules` | Sends reminders as soon as they become due, following the original reminder rules.        |

The mode is configured in `app/config.py`.
The engine accepts an optional learning agent through `check_tasks(repo, db, now, agent=None)`. When no agent is supplied, the engine continues to work in rules mode. When an agent is supplied, the engine uses the smart timing decision process.
The engine also checks whether a held reminder has reached its next evaluation time. If the waiting period has not ended, the reminder remains on hold. Otherwise, the learner and safety shield evaluate it again.

### Learning from ignored reminders

The `mark_ignored()` function identifies notifications that have received no response within the configured 30-minute period.
These notifications are recorded as `ignored`. When a learning agent is available and the notification has a saved state, the agent learns from that response.
This allows the system to learn from both explicit user actions and a lack of response.

## 7. Learning from Real User Responses

The system uses the existing reward values from the Q-learning environment to learn from user feedback.

| User response | Reward |
|---------------|-------:|
| Done          | +2     |
| Opened        | +1     |
| Ignored       | 0      |
| Snoozed       | -0.5   |
| Dismissed     | -1     |

The `learn_from_response()` function in `app/smart.py` updates the Q-value associated with the saved state and the `SEND_NOW` action.

For example, if the initial Q-value is 0, the learning rate is 0.1, and the user marks the reminder as Done, the updated value is:

\[
Q_{\text{new}} = Q_{\text{old}} + \alpha(r-Q_{\text{old}})
\]

\[
Q_{\text{new}} = 0 + 0.1(2-0)=0.2
\]

This demonstrates how feedback influences the model's future decisions.

### Saving the live model

The system uses two Q-table files:
- `experiments/results/q_table_everyone.npy` provides the initial trained model.
- `data/q_table_live.npy` stores the model that continues learning from real user responses.

When the application starts for the first time, it copies the initial model to the live model file. On subsequent starts, it loads the existing live model so that previously learned information is retained.
The live model is saved after learning updates and background checks.
The live Q-table must be added to `.gitignore` because it contains information learned from an individual user's behaviour. It should not be committed to GitHub.

## 8. Developing the Web Application

I implemented the web application in `app/web.py` using FastAPI.
The application performs two main responsibilities: serving the web interface and running the reminder engine in the background.

### Background scheduling

I used APScheduler's `BackgroundScheduler` to execute the reminder checks automatically at the configured interval.
The application performs an initial check when it starts and continues checking for new reminders in the background. This allows the web server to respond to browser requests while the reminder engine runs.
The scheduler is stopped when the application shuts down.

### Thread safety

The engine and the web interface may attempt to update the learning model at the same time. To prevent conflicting updates, I used a `threading.Lock`.
The lock ensures that only one operation updates the learner at a time.

### REST API endpoints

I implemented three main endpoints.

| HTTP method | Endpoint                                       | Purpose                                                                  |
|-------------|------------------------------------------------|--------------------------------------------------------------------------|
| `GET`       | `/`                                            | Returns the reminder web page.                                           |
| `GET`       | `/api/notifications`                           | Returns the latest sent reminders and the waiting list as JSON.          |
| `POST`      | `/api/notifications/{notification_id}/respond` | Records a user response and updates the relevant task or learning model. |

The response endpoint accepts `done`, `snoozed`, or `dismissed`.
I used a Pydantic model with `Literal` to validate the permitted response values. Invalid responses are rejected with HTTP status `422`, while requests for nonexistent notification IDs receive status `404`.
When a user selects Done, the system records the response and changes the task status to `done`. This prevents the task from being treated as pending in future checks.

## 9. Building the Web Interface

I created `app/static/index.html` using HTML, CSS, and JavaScript.

The interface contains two main sections:
- **Sent to you:** Displays the most recent reminders, their sending times, explanations, and user responses.
- **Waiting for a better moment:** Displays reminders that the learner has temporarily held.

Each unanswered sent reminder provides three buttons.

| Button  | Function                                                    |
|---------|-------------------------------------------------------------|
| Done    | Records completion and marks the task as done.              |
| Snooze  | Records that the user wants to delay or defer the reminder. |
| Dismiss | Records that the user does not want the reminder.           |

The JavaScript function `refresh()` retrieves notification data from the API and updates the page. It runs initially and then repeats every five seconds.
The `respond()` function sends the selected response to the server and refreshes the interface. Therefore, the user does not need to reload the page manually.

### Cross-site scripting protection

I used JavaScript's `textContent` property to display task messages and explanations rather than inserting user-controlled text directly as HTML.
This reduces the risk of cross-site scripting (XSS), because task titles are displayed as text instead of being interpreted as executable HTML.

## 10. Testing the Implementation

I created two new test files to verify the smart timing and web application functionality.

### Smart timing tests

The tests in `tests/test_smart.py` verify:

- Rules mode sends a due reminder immediately and records its reason.
- The learner can hold a reminder for 30 minutes.
- A held reminder is not sent before its waiting period ends.
- The safety shield forces a reminder to be sent when the deadline becomes too close.
- Normal reminders are not sent during quiet hours.
- A Done response updates the relevant Q-value as expected.
- An ignored reminder also updates the learning model.

I used a controlled test learner that always prefers a specified action. This makes it possible to test the engine's behaviour without depending on unpredictable decisions from a trained model.
For example, even if the learner always prefers to wait, the safety shield must force a reminder to be sent when waiting is no longer permitted.

### Web application tests

The tests in `tests/test_web.py` verify:

- The API returns saved reminders.
- The waiting list is returned correctly.
- A Done response is saved in the database.
- The corresponding task is marked as completed.
- Invalid response values are rejected with status `422`.
- A nonexistent notification returns status `404`.

I used FastAPI's `TestClient`, `tmp_path`, and `monkeypatch` to test the API with temporary databases and task files without modifying the actual runtime data.

### Running the tests

From the project directory, with the virtual environment activated, I used:

```powershell
python -m pytest
```

The expected result is:

```text
39 passed, 1 warning
```

The warning described in the guide is a deprecation warning originating from the testing library dependencies, rather than from the application code.

## 11. Running the Application

### Install the required packages

```powershell
pip install fastapi uvicorn httpx
pip freeze > requirements.txt
```

### Generate sample tasks

```powershell
python data/make_tasks.py
```

### Start the web application

If I want a clean test database, I stop any running server first and delete the existing database:

```powershell
del data\notifications.db
python -m app.web
```

The server starts on port `8000`.
I can open the interface on my laptop using:

```text
http://localhost:8000
```

To add a task, I open another terminal, activate the virtual environment, and run:

```powershell
python -m app.add_task "Call supervisor" 62 low
```

The new task can then be picked up by the background reminder engine when its reminder window opens.

### Accessing the application from a phone

To access the interface from my phone, I connect both devices to the same Wi-Fi network and find my laptop's IPv4 address using:

```powershell
ipconfig
```

I then open the following address in the phone's browser, replacing the example IP address with my laptop's actual IPv4 address:

```text
http://192.168.1.23:8000
```

Windows Firewall may need to allow Python to accept connections on private networks. Some university Wi-Fi networks also prevent devices from communicating with each other.
When both devices can access the server, responses made on the phone are reflected on the laptop because both interfaces use the same backend and database.

## 12. Important Software Design Concepts

### Online learning

Online learning means that the model continues to update after its initial training. Each real user response provides feedback that can influence future reminder decisions.
The updated Q-table is saved to `data/q_table_live.npy`, allowing the model to retain its learning across application restarts.

### Transfer learning and cold-start handling

A new user's model starts from the previously trained `q_table_everyone.npy` rather than an empty Q-table.
This gives the system an initial understanding of reminder timing before enough individual feedback has been collected. The live model then adapts to the user's own responses.

### Explainable AI

Each sent reminder includes a reason describing why it was delivered at that moment. This makes the system's timing decisions more understandable to the user.

### REST API

The web interface communicates with the Python backend through HTTP endpoints. The same endpoints could later be used by the team's mobile application or voice assistant.

### Separation of concerns

The implementation separates smart decision-making, database operations, task management, engine execution, API handling, and user-interface presentation into different files.
This makes the system easier to maintain and allows individual components to be changed without rewriting the entire application.

### Repository pattern

The reminder engine accesses tasks through the repository interface rather than directly reading the JSON file. The current fake repository can later be replaced by a repository that retrieves tasks from the team's knowledge graph.

### Thread safety

The threading lock prevents the background engine and a user interaction from modifying the learning model simultaneously.

### Idempotency

The unique reminder key prevents the same reminder from being recorded multiple times during repeated scheduler checks. Persistent database records also help the application avoid resending reminders that have already been recorded after a restart.

## 13. Connection to the Research Project

This implementation advances the Proactive Notification and Interaction System from simulated reminder timing towards a usable, feedback-driven reminder component.
The previously trained Q-learning model provides the initial timing policy, while the safety shield enforces restrictions on the learner's decisions. The reminder engine coordinates task evaluation, sending, and holding. The web interface provides a way for users to respond, and those responses update the personalized model.
The current implementation still uses a fake task repository backed by a JSON file. In a later stage, this repository can be replaced with an integration to the team's knowledge graph, allowing the system to use real tasks and commitments extracted from stored conversations.
This creates a foundation for connecting intelligent reminder timing with the wider personal AI assistant.

## 14. Lessons Learned

- How to integrate a trained Q-learning agent into a running reminder engine.
- How a safety shield can restrict actions chosen by a learning model.
- How to hold reminders and reconsider them as deadlines approach.
- How to generate explanations for reminder timing decisions.
- How to update a Q-table using real user responses.
- How to initialize a personalized model from a shared trained model.
- How to persist learning across application restarts.
- How to extend an SQLite database without deleting existing records.
- How to build a FastAPI application with REST endpoints.
- How to run scheduled background jobs alongside a web server.
- How to use threading locks to protect shared learning state.
- How to develop a responsive HTML, CSS, and JavaScript interface.
- How to test API endpoints without starting a separate server.
- Why private user-specific learning data should be excluded from GitHub.
- How the repository pattern supports future integration with a knowledge graph.

## 15. Final Outcome

The resulting system combines intelligent reminder timing, safety restrictions, automatic scheduling, persistent storage, a web interface, and online learning from user responses.
The application can send reminders immediately or hold them for a better moment, explain its decisions, record user feedback, and update its personalized learning model. It also supports rules mode for comparison with smart mode.
Before proceeding to the next integration stage, I need to verify that all tests pass, confirm that the web interface works on both my laptop and phone, observe at least one reminder being held, and ensure that `data/q_table_live.npy` and `data/notifications.db` are excluded from GitHub.
