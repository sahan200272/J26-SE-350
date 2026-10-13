"""Train one model on all pretend users, then test how well it helps a brand-new user.""" 
import copy 
 
import matplotlib.pyplot as plt 
 
from app.agent import QAgent 
from app.baselines import send_when_due 
from app.environment import ReminderEnv 
from app.simulation import PERSONAS, PretendUser 
from app.training import evaluate, train 
 
NEW_USER = "night_owl_student" 
SEEDS = [1, 2, 3] 
PRACTICE = [0, 1000, 2000, 5000, 10000, 20000] 
 
 
def world(name, seed): 
    return ReminderEnv(PretendUser(name, seed=seed), seed=seed + 1) 
 
 
def response_rate(name, choose): 
    return evaluate(world(name, 500), choose, use_shield=True)["response rate"] 
 
 
# 1. One model for everyone 
everyone = train([world(name, i) for i, name in enumerate(PERSONAS)], QAgent(seed=1), 120000) 
everyone.save("experiments/results/q_table_everyone.npy")

print("One model for everyone (response rate, safety net on)") 
print(f"{'':20}{'everyone':>10}{'send now':>10}")

for name in PERSONAS: 
    print(f"{name:20}{response_rate(name, everyone.choose):>10.2f}{response_rate(name, send_when_due):>10.2f}") 


# 2. A brand-new user: start from zero, or with a head start from everyone else? 
from_zero = [0.0] * len(PRACTICE) 
from_head_start = [0.0] * len(PRACTICE)

for seed in SEEDS:
    others = [world(name, seed * 10 + i) for i, name in enumerate(PERSONAS) if name != NEW_USER] 
    head_start = train(others, QAgent(seed=seed), 120000)

    for i, practice in enumerate(PRACTICE): 
        new_user = [world(NEW_USER, seed * 100 + i)] 
        fresh = train(new_user, QAgent(seed=seed), practice) 
        warm = train(new_user, copy.deepcopy(head_start), practice, explore=0.1, nudge=0.05) 
        from_zero[i] += response_rate(NEW_USER, fresh.choose) / len(SEEDS) 
        from_head_start[i] += response_rate(NEW_USER, warm.choose) / len(SEEDS) 
 
print(f"\nNew user: {NEW_USER} (response rate, average of {len(SEEDS)} runs)") 
print(f"{'practice':>10}{'from zero':>12}{'head start':>12}")

for practice, a, b in zip(PRACTICE, from_zero, from_head_start): 
    print(f"{practice:>10}{a:>12.2f}{b:>12.2f}") 
 
plt.figure(figsize=(8, 4.5)) 
plt.plot(PRACTICE, from_head_start, marker="o", label="starts from the everyone-else model") 
plt.plot(PRACTICE, from_zero, marker="o", label="starts from zero") 
plt.axhline(response_rate(NEW_USER, send_when_due), linestyle="--", color="grey", label="send when due") 
plt.xlabel("Practice reminders with the new user") 
plt.ylabel("Response rate") 
plt.title(f"A head start helps a brand-new user ({NEW_USER})") 
plt.ylim(0, 0.7) 
plt.legend() 
plt.tight_layout() 
plt.savefig("experiments/results/new_user_head_start.png")

print("\nSaved experiments/results/new_user_head_start.png")