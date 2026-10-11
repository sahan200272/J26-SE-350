"""The learner: a Q-table and the rules for using and updating it.""" 
import random 
 
import numpy as np 
 
from app.state import N_STATES 
 
 
class QAgent: 
    def __init__(self, n_actions=3, alpha=0.1, gamma=0.95, epsilon=0.3, seed=None): 
        self.Q = np.zeros((N_STATES, n_actions))  # the notebook: one row per situation 
        self.n_actions = n_actions 
        self.alpha = alpha        # learning rate: how big each nudge is 
        self.gamma = gamma        # how much future points count 
        self.epsilon = epsilon    # how often to try a random choice 
        self.rng = random.Random(seed) 
 
    def choose(self, state): 
        """Usually pick the best-scoring choice; sometimes explore.""" 
        if self.rng.random() < self.epsilon: 
            return self.rng.randrange(self.n_actions) 
        return int(np.argmax(self.Q[state])) 
 
    def learn(self, state, action, reward, next_state, finished): 
        """Nudge one score towards what actually happened.""" 
        future = 0.0 if finished else np.max(self.Q[next_state]) 
        target = reward + self.gamma * future 
        self.Q[state, action] += self.alpha * (target - self.Q[state, action]) 
 
    def save(self, path): 
        np.save(path, self.Q) 
 
    def load(self, path): 
        self.Q = np.load(path) 