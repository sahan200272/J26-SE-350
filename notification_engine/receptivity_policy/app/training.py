"""Practice rounds: run reminders, learn from them, and measure how well a policy does.""" 
from app.environment import SEND_NOW 
 
ENGAGED = {"opened", "done", "snoozed"} 
 
 
def run_episode(env, agent, learn=True): 
    """Play one reminder from start to finish. Returns (total points, what happened).""" 
    state = env.reset() 
    total = 0.0 
    while True: 
        action = agent.choose(state) 
        next_state, reward, finished, outcome = env.step(action) 
        if learn: 
            agent.learn(state, action, reward, next_state, finished) 
        total += reward 
        state = next_state 
        if finished: 
            return total, outcome 
 
 
def evaluate(env, choose, episodes=5000): 
    """Measure a way of choosing over many reminders, without learning.""" 
    points, engaged, missed = 0.0, 0, 0 
    for _ in range(episodes): 
        state = env.reset() 
        while True: 
            state, reward, finished, outcome = env.step(choose(state)) 
            points += reward 
            if finished: 
                engaged += outcome in ENGAGED 
                missed += outcome == "missed" 
                break 
    return {"average points": points / episodes, 
            "response rate": engaged / episodes, 
            "missed deadlines": missed / episodes} 
 
 
def always_send_now(state): 
    """The simplest possible baseline: send the moment a reminder is due.""" 
    return SEND_NOW