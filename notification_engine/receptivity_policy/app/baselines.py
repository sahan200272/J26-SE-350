"""Simpler ways of choosing when to send, to compare your learner against.""" 
import random 
 
from app.environment import SEND_NOW, WAIT_30 
from app.simulation import DAY_PARTS 
from app.state import N_STATES 
from app.training import always_send_now 
 
STATES_PER_PART = N_STATES // len(DAY_PARTS)     # 120 situation numbers per part of the day 
MORNING = DAY_PARTS.index("morning") 
 
 
def send_when_due(state, allowed): 
    """Your original rule-based system: send as soon as the reminder is due.""" 
    return always_send_now(state, allowed) 
 
 
class RandomTiming: 
    """Pick any allowed move at random.""" 
 
    def __init__(self, seed=None): 
        self.rng = random.Random(seed) 
 
    def __call__(self, state, allowed): 
        return self.rng.choice(allowed) 
 
 
def mornings_only(state, allowed): 
    """A fixed rule many apps use: wait for the morning, then send.""" 
    part = state // STATES_PER_PART 
    if part == MORNING and SEND_NOW in allowed: 
        return SEND_NOW 
    if WAIT_30 in allowed:
        return WAIT_30 
    return SEND_NOW            # the deadline is too close to wait