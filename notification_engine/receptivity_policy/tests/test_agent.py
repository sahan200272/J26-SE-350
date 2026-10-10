from app.agent import QAgent 
 
 
def test_learning_moves_the_score_towards_the_reward(): 
    agent = QAgent() 
    agent.learn(state=5, action=0, reward=1.0, next_state=5, finished=True) 
    assert abs(agent.Q[5, 0] - 0.1) < 1e-9        # 0 + 0.1 * (1 - 0) 
 
 
def test_with_no_exploring_it_picks_the_best_score(): 
    agent = QAgent(epsilon=0.0) 
    agent.Q[7] = [0.2, 0.9, 0.1] 
    assert agent.choose(7) == 1