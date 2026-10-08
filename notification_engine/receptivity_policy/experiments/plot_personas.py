"""Draw how often each pretend user responds at each hour of a weekday."""
import os

import matplotlib.pyplot as plt

from app.simulation import PERSONAS, PretendUser

ENGAGED = {"opened", "done", "snoozed"}
TRIES = 500

os.makedirs("experiments/results", exist_ok=True)

plt.figure(figsize=(10, 5))
for name in PERSONAS:
    user = PretendUser(name, seed=7)
    rates = []
    for hour in range(24):
        answers = [user.respond(hour, False, "normal", 0) for _ in range(TRIES)]
        rates.append(sum(a in ENGAGED for a in answers) / TRIES)
    plt.plot(range(24), rates, marker="o", label=name)

plt.xlabel("Hour of the day")
plt.ylabel("Share of notifications responded to")
plt.title("How each pretend user responds through a weekday")
plt.xticks(range(24))
plt.ylim(0, 1)
plt.legend()
plt.tight_layout()
plt.savefig("experiments/results/personas.png")
print("Saved experiments/results/personas.png")