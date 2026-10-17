from app.environment import MISSED_PENALTY, SEND_NOW, WAIT_2H, ReminderEnv 
from app.simulation import PretendUser 
 
 
def make_env(): 
    env = ReminderEnv(PretendUser("morning_person", seed=1), seed=2) 
    env.reset() 
    return env 
 
 
def test_sending_finishes_the_reminder(): 
    env = make_env() 
    _, _, finished, outcome = env.step(SEND_NOW) 
    assert finished 
    assert outcome in {"opened", "done", "snoozed", "dismissed", "ignored"} 
 
 
def test_waiting_uses_up_time(): 
    env = make_env() 
    env.minutes_left = 10 * 60 
    env.step(WAIT_2H) 
    assert env.minutes_left == 8 * 60 
 
 
def test_waiting_past_the_deadline_is_punished(): 
    env = make_env() 
    env.minutes_left = 60 
    _, reward, finished, outcome = env.step(WAIT_2H) 
    assert finished and outcome == "missed" and reward == MISSED_PENALTY