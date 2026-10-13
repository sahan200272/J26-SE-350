"""What does the safety net change? Same methods, same reminders, with and without it.""" 
from app.agent import QAgent 
from app.baselines import RandomTiming 
from app.environment import ReminderEnv 
from app.simulation import PretendUser 
from app.training import evaluate, train 
 
PERSONA = "morning_person" 
 
 
def world(seed): 
    return ReminderEnv(PretendUser(PERSONA, seed=seed), seed=seed + 1) 
 
 
print(f"{PERSONA}, 5,000 test reminders each") 
print(f"{'':32}{'response rate':>15}{'missed':>9}{'rule breaks':>13}") 
for use_shield in [False, True]: 
    label = "with safety net" if use_shield else "no safety net" 
    learner = train([world(1)], QAgent(seed=3), 60000, use_shield=use_shield) 
    for name, choose in [("Random timing", RandomTiming(5)), ("Your learner", 
learner.choose)]: 
        r = evaluate(world(10), choose, use_shield=use_shield) 
        print(f"{name + ', ' + label:32}{r['response rate']:>15.2f}" 
              f"{r['missed deadlines']:>9.3f}{r['rule breaks']:>13.3f}")