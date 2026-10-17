"""The fair race: every method, every pretend user, same test reminders, safety net on.""" 
import csv 
import statistics 
 
import matplotlib.pyplot as plt 
 
from app.agent import QAgent 
from app.baselines import RandomTiming, mornings_only, send_when_due 
from app.environment import ReminderEnv 
from app.simulation import PERSONAS, PretendUser 
from app.training import evaluate, train 
 
SEEDS = [1, 2, 3] 
EPISODES = 60000 
METHODS = ["Send when due", "Random timing", "Mornings only", "Learner, no planning", "Q-learner"]

def world(name, seed): 
    return ReminderEnv(PretendUser(name, seed=seed), seed=seed + 1) 
 
 
rows = [] 
for name in PERSONAS: 
    for seed in SEEDS: 
        practice = [world(name, seed)] 
        learner = train(practice, QAgent(seed=seed), EPISODES) 
        no_planning = train(practice, QAgent(gamma=0.0, seed=seed), EPISODES) 
        choosers = {"Send when due": send_when_due, 
                    "Random timing": RandomTiming(seed), 
                    "Mornings only": mornings_only, 
                    "Learner, no planning": no_planning.choose, 
                    "Q-learner": learner.choose} 
        for method, choose in choosers.items(): 
            test = world(name, seed + 1000)          # fresh reminders, same for every method 
            result = evaluate(test, choose, use_shield=True) 
            rows.append({"user": name, "seed": seed, "method": method, **result}) 
    print(f"finished {name}") 
 
with open("experiments/results/race.csv", "w", newline="") as f: 
    writer = csv.DictWriter(f, fieldnames=rows[0].keys()) 
    writer.writeheader() 
    writer.writerows(rows) 
 
 
def average(method, key, user=None): 
    values = [r[key] for r in rows if r["method"] == method and (user is None or r["user"] == user)] 
    spread = statistics.stdev(values) if len(values) > 1 else 0.0 
    return statistics.mean(values), spread 
 
 
print(f"\nAll users, {len(SEEDS)} runs each (mean +/- spread)") 
print(f"{'':22}{'response rate':>16}{'points':>14}{'missed':>8}{'rule breaks':>13}")

for method in METHODS: 
    rate, rate_sd = average(method, "response rate") 
    pts, pts_sd = average(method, "average points") 
    missed, _ = average(method, "missed deadlines") 
    breaks, _ = average(method, "rule breaks") 
    print(f"{method:22}{rate:>10.2f} +/-{rate_sd:4.2f}{pts:>8.2f} +/- {pts_sd:4.2f}{missed:>8.2f}{breaks:>13.2f}") 
 
print("\nResponse rate by user") 
print(f"{'':20}" + "".join(f"{m[:12]:>14}" for m in METHODS))

for name in PERSONAS: 
    print(f"{name:20}" + "".join(f"{average(m, 'response rate', name)[0]:>14.2f}" for m in METHODS)) 
 
# Chart: one group of bars per user, one bar per method 
width = 0.16 
plt.figure(figsize=(11, 5)) 
for i, method in enumerate(METHODS): 
    heights = [average(method, "response rate", name)[0] for name in PERSONAS] 
    positions = [x + (i - 2) * width for x in range(len(PERSONAS))] 
    plt.bar(positions, heights, width, label=method)

plt.xticks(range(len(PERSONAS)), PERSONAS) 
plt.ylabel("Response rate") 
plt.title("Response rate by pretend user and method (safety net on)") 
plt.ylim(0, 0.8) 
plt.legend(ncol=5, loc="upper center", fontsize=8) 
plt.tight_layout() 
plt.savefig("experiments/results/race.png")

print("\nSaved experiments/results/race.png and race.csv")