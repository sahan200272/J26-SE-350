### 1. Why does each pretend user have its own seeded random generator?

1. Each pretend user has its own random number generator so that one user's random actions do not directly affect another user's random sequence.
2. With a seed, the same experiment gives the same results every time. Without a seed, running it twice would give different numbers and a different chart, so we could not tell if a change came from our code or from luck.
3. This makes our experiments easier to test, compare, and debug because we can identify whether a change in the results comes from our code or from different random outcomes.

### 2. What is a state in Q-learning?

1. A state represents the current situation of a reminder.
2. In my implementation, each state is described using five facts: part of the day, weekday or weekend, priority, time remaining until the deadline, and the number of reminders already sent today.
3. Each fact is divided into a small number of categories to keep the model simple.
4. There are 720 possible states because \(6 \times 2 \times 4 \times 5 \times 3 = 720\).
5. The `encode_state()` function converts these five facts into a unique number from 0 to 719. This number identifies a row in the Q-table.

### 3. What is the Q-table?

1. The Q-table stores the scores of different actions for each possible state.
2. My Q-table contains 720 rows and 3 columns.
3. Each row represents a situation, and each column represents an action: send now, wait 30 minutes, or wait 2 hours.
4. Each cell stores the estimated value of choosing a particular action in a particular situation.
5. Initially, all scores are zero because the model has not learned anything yet.

### 4. Why does the model need an environment?

1. The environment represents the practice world in which the model learns how to send reminders.
2. The `reset()` function starts a new reminder with a random time, day, priority, deadline, and number of reminders already sent.
3. The `step()` function performs the selected action and returns the next state, reward, whether the episode has finished, and the outcome.
4. When the model waits, the clock moves forward and the remaining time decreases. If the deadline passes before the reminder is sent, the model receives a penalty.
5. The environment uses the `PretendUser` class from Hands-on 1 to simulate how users respond to reminders.

### 5. What are actions and rewards?

1. An action is a decision made by the model. There are three possible actions: send now, wait 30 minutes, and wait 2 hours.
2. A reward is a numerical score given to the model based on what happens.
3. Completing a task receives a reward of +2.0, opening a reminder receives +1.0, ignoring receives 0.0, snoozing receives -0.5, and dismissing receives -1.0.
4. Waiting costs -0.01 points to discourage unnecessary waiting, while missing a deadline results in a penalty of -3.0.
5. These reward values encourage the model to find a suitable reminder time, obtain positive user responses, and avoid missing deadlines.

### 6. What is an episode?

1. An episode represents one complete reminder attempt.
2. It starts when the environment creates a new reminder and ends when the reminder is sent or its deadline passes.
3. During an episode, the model observes the current state, chooses an action, receives a reward, and learns from the result.
4. Repeating many episodes helps the model improve its decisions.

### 7. How does the Q-learning agent learn?

1. The `QAgent` class contains the Q-table and the methods used to choose actions and update scores.
2. The `choose()` function selects an action based on the current Q-table, but it sometimes chooses randomly to discover better actions.
3. The `learn()` function updates the score of the selected action using the reward received and the best estimated future reward.
4. The learning rate, alpha (\(\alpha = 0.1\)), controls how much the model updates its existing score.
5. The discount factor, gamma (\(\gamma = 0.95\)), controls how much future rewards influence the current decision.
6. Epsilon (\(\epsilon = 0.3\) initially) controls how often the model explores by choosing a random action.
7. During training, epsilon and alpha decrease gradually. This allows the model to explore more at the beginning and make smaller updates as it learns.

### 8. Why is waiting important in Q-learning?

1. Waiting allows the model to move from the current state to a future state.
2. For example, if the model waits in the afternoon, it might reach the evening or the next morning, when the user is more likely to respond.
3. The model considers the future value of the new state when deciding whether waiting is worthwhile.
4. This allows the model to plan ahead instead of considering only the immediate reward.
5. This is an important reason for using Q-learning in my adaptive reminder timing system.

### 9. What are training and evaluation?

1. The `run_episode()` function runs one reminder episode and updates the Q-table when learning is enabled.
2. The `evaluate()` function measures the model's performance over many reminders without updating the Q-table.
3. The `always_send_now()` function provides a baseline strategy that sends every reminder immediately.
4. The model is trained for 60,000 episodes and evaluated using 5,000 test reminders.
5. Both the trained model and the baseline use the same random seeds for the test environment and pretend user. This helps make the comparison fair.
6. The evaluation measures average points, response rate, and missed deadlines.
7. The learning curve shows how the average reward changes as the model practises.

### 10. What did I learn from the experiments?

1. I trained the model using different pretend users, including `morning_person` and `evening_person`.
2. The model can learn different reminder timing strategies depending on each user's response patterns.
3. The morning person should receive reminders in the morning, while the evening person should receive reminders in the evening, if the learned results show these patterns.
4. I also tested `nine_to_five` and my own pretend user to observe how different response patterns affect the learned strategy.
5. I experimented with a lower gamma value of 0.5 to investigate how reducing the importance of future rewards affects reminder timing.
6. These experiments help me understand how the learning rate, discount factor, user behaviour, and exploration strategy affect the model's performance.

### 11. Why do we test on fresh reminders?

1. The model should be tested on reminders that were not used to update its Q-table during training.
2. This helps measure how well the learned strategy performs on new situations instead of only measuring its performance on practice episodes.
3. Using the same test seeds for the learner and baseline also helps reduce differences caused by random user behaviour.
4. Therefore, evaluation provides a more useful comparison between the learned strategy and the send-now baseline.

### 12. What are the four main parts of my Q-learning model?

1. **State:** The five facts describing the current reminder situation, combined into one number representing one of 720 possible states.
2. **Action:** One of three decisions: send now, wait 30 minutes, or wait 2 hours.
3. **Reward:** The numerical feedback received after an action, based on user response, waiting, or missing the deadline.
4. **Episode:** One complete reminder attempt, from the starting situation until the reminder is sent or the deadline passes.
