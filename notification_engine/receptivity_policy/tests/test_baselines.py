from app.baselines import mornings_only, send_when_due 
from app.environment import SEND_NOW, WAIT_30 
from app.state import encode_state

def test_mornings_only_sends_in_the_morning_and_waits_otherwise(): 
    morning = encode_state(10, False, "normal", 36 * 60, 0) 
    afternoon = encode_state(15, False, "normal", 36 * 60, 0) 
    assert mornings_only(morning, [0, 1, 2]) == SEND_NOW 
    assert mornings_only(afternoon, [0, 1, 2]) == WAIT_30


def test_send_when_due_waits_only_if_sending_is_blocked(): 
    state = encode_state(10, False, "normal", 36 * 60, 0) 
    assert send_when_due(state, [0, 1, 2]) == SEND_NOW 
    assert send_when_due(state, [1, 2]) == WAIT_30