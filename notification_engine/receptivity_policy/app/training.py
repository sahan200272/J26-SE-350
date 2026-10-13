"""Practice rounds: run reminders, learn from them, and measure how well a policy 
does.""" 
import random 
 
from app.environment import SEND_NOW, WAIT_30 
from app.shield import allowed_for 
 
ENGAGED = {"opened", "done", "snoozed"} 
ALL_MOVES = [0, 1, 2] 
 
 
def moves_for(env, use_shield): 
    return allowed_for(env) if use_shield else ALL_MOVES 
 
 
def run_episode(env, agent, learn=True, use_shield=False): 
    """Play one reminder from start to finish. Returns (total points, what happened).""" 
    state = env.reset() 
    allowed = moves_for(env, use_shield) 
    total = 0.0 
    while True: 
        action = agent.choose(state, allowed) 
        next_state, reward, finished, outcome = env.step(action) 
        next_allowed = moves_for(env, use_shield) 
        if learn: 
            agent.learn(state, action, reward, next_state, finished, next_allowed) 
        total += reward 
        state, allowed = next_state, next_allowed 
        if finished: 
            return total, outcome


def train(envs, agent, episodes, use_shield=True, seed=0, explore=0.3, nudge=0.1): 
    """Practise on a list of worlds (one per pretend user), picking one at random each 
round.""" 
    rng = random.Random(seed) 
    for episode in range(episodes): 
        progress = episode / episodes                        # goes from 0 to 1 
        agent.epsilon = max(0.02, explore * (1 - progress / 0.7))   # explore less over time
        agent.alpha = max(0.01, nudge * (1 - progress))             # smaller nudges over time 
        run_episode(rng.choice(envs), agent, use_shield=use_shield) 
    agent.epsilon = 0.0          # finished practising: no more random tries 
    return agent 
 
 
def evaluate(env, choose, episodes=5000, use_shield=False): 
    """Measure a way of choosing over many reminders, without learning.""" 
    points, engaged, missed, rule_breaks = 0.0, 0, 0, 0 
    for _ in range(episodes): 
        state = env.reset() 
        while True: 
            action = choose(state, moves_for(env, use_shield)) 
            if action == SEND_NOW and SEND_NOW not in allowed_for(env): 
                rule_breaks += 1          # a send the safety net would have blocked 
            state, reward, finished, outcome = env.step(action) 
            points += reward 
            if finished: 
                engaged += outcome in ENGAGED 
                missed += outcome == "missed" 
                break 
    return {"average points": points / episodes, 
            "response rate": engaged / episodes, 
            "missed deadlines": missed / episodes, 
            "rule breaks": rule_breaks / episodes} 
 
 
def always_send_now(state, allowed=ALL_MOVES): 
    """Baseline: send as soon as it's allowed (your original rule-based system).""" 
    return SEND_NOW if SEND_NOW in allowed else WAIT_30
