"""Train the learner on one pretend user, then show what it learned.""" 
import sys 
 
import matplotlib.pyplot as plt 
 
from app.agent import QAgent 
from app.environment import ACTION_NAMES, ReminderEnv 
from app.simulation import DAY_PARTS, PretendUser 
from app.state import encode_state 
from app.training import always_send_now, evaluate, run_episode 
 
PERSONA = sys.argv[1] if len(sys.argv) > 1 else "morning_person" 
EPISODES = 60000 
WINDOW = 1000 
 
# 1. Practise 
env = ReminderEnv(PretendUser(PERSONA, seed=1), seed=2) 
agent = QAgent(seed=3)
#agent = QAgent(gamma=0.5, seed=3)          # An impatient learner, who doesn't care about the future.

averages, window = [], []

for episode in range(EPISODES): 
    progress = episode / EPISODES                         # goes from 0 to 1

    agent.epsilon = max(0.02, 0.3 * (1 - progress / 0.7))  # explore less over time 
    agent.alpha = max(0.01, 0.1 * (1 - progress))          # make smaller nudges over time

    points, _ = run_episode(env, agent) 
    window.append(points)

    if len(window) == WINDOW: 
        averages.append(sum(window) / WINDOW) 
        window = []
# 2. Save the trained Q-table      
agent.save(f"experiments/results/q_table_{PERSONA}.npy") 
 
# 3. Save the learning curve
plt.figure(figsize=(9, 4)) 
plt.plot(
    [(i + 1) * WINDOW for i in range(len(averages))], 
    averages,
) 
plt.xlabel("Practice reminders") 
plt.ylabel("Average points (per 1,000 reminders)") 
plt.title(f"Learning curve: {PERSONA}") 
plt.tight_layout() 
plt.savefig(
    f"experiments/results/learning_curve_{PERSONA}.png"
) 
 
# 4. Compare with the simplest baseline, using fresh reminders and no exploring 
agent.epsilon = 0.0

test_env = ReminderEnv(PretendUser(PERSONA, seed=10), seed=11) 
learned = evaluate(test_env, agent.choose)

test_env = ReminderEnv(PretendUser(PERSONA, seed=10), seed=11) 
baseline = evaluate(test_env, always_send_now)

print(f"\nResults for {PERSONA} (5,000 test reminders each)") 
print(f"{'':20}{'learner':>10}{'send now':>10}")

for key in learned: 
    print(f"{key:20}{learned[key]:>10.2f}{baseline[key]:>10.2f}") 
 
# 5. Inspect the model's choices at different times(what does it choose on a weekday, normal priority, 24-48 h left?) 
print(
    "\nWeekday, normal priority, 24-48 h left, 0-2 reminders sent today:"
)

for hour, part in zip([3, 7, 10, 13, 15, 20], DAY_PARTS): 
    state = encode_state(hour, False, "normal", 36 * 60, 0) 
    print(f"  {part:10} -> {ACTION_NAMES[agent.choose(state)]}") 