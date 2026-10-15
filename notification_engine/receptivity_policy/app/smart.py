"""Smart timing: the learner and the safety net decide when a due reminder goes out.""" 
from app.environment import REWARDS, SEND_NOW, WAIT_2H, WAIT_30 
from app.shield import allowed_actions 
from app.simulation import day_part 
from app.state import encode_state 
 
WAIT_MINUTES = {WAIT_30: 30, WAIT_2H: 120} 
 
 
def decide(agent, task, now, sent_today): 
    minutes_left = int((task.deadline - now).total_seconds() // 60) 
    state = encode_state(now.hour, now.weekday() >= 5, task.priority, minutes_left, sent_today) 
    allowed = allowed_actions(now.hour, task.priority, minutes_left, sent_today) 
    action = agent.choose(state, allowed) 
    return state, action, explain(action, allowed, now) 
 
 
def explain(action, allowed, now): 
    if action != SEND_NOW: 
        if SEND_NOW not in allowed: 
            return f"Holding for {WAIT_MINUTES[action]} min: quiet hours or daily limit" 
        return f"Holding for {WAIT_MINUTES[action]} min: a better moment is likely soon" 
    if allowed == [SEND_NOW]: 
        return "Sent now: the deadline is too close to wait" 
    return f"Sent now: your learner rated sending this {day_part(now.hour)} better than waiting" 
 
 
def learn_from_response(agent, state, response): 
    agent.learn(state, SEND_NOW, REWARDS[response], state, finished=True)