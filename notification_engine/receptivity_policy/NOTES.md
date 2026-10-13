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

1. State: The five facts describing the current reminder situation, combined into one number representing one of 720 possible states.
2. Action: One of three decisions: send now, wait 30 minutes, or wait 2 hours.
3. Reward: The numerical feedback received after an action, based on user response, waiting, or missing the deadline.
4. Episode: One complete reminder attempt, from the starting situation until the reminder is sent or the deadline passes.

### 13. What is the safety net (shield)?

1. The safety net is a set of rules placed between the Q-learning agent and the user.
2. Before the learner chooses an action, the safety net checks which actions are safe and allowed.
3. The learner can only choose from the allowed actions, so it cannot break the safety rules even if it has learned a bad strategy.
4. This is called shielded reinforcement learning because the shield protects the user from unsafe decisions.
5. The safety net is important because the learner mainly tries to maximise rewards, so without restrictions it could sometimes wait too long, send reminders during quiet hours, or send too many reminders.

### 14. What are the four safety rules?

1. Never wait past the deadline: The learner can wait 30 minutes only when more than 30 minutes remain, and it can wait 2 hours only when more than 2 hours remain.
2. Urgent and nearly due: If a reminder is critical or high priority and has one hour or less remaining, the learner must send it immediately.
3. Quiet hours: Normal reminders cannot be sent between 22:00 and 07:00. Critical reminders are allowed during this period.
4. Daily limit: After 6 reminders have been sent in one day, normal and low-priority reminders cannot be sent immediately and must wait until the next day.
5. When safety rules conflict, the deadline rule has priority. This means a reminder will be sent rather than missed if waiting would cause it to pass its deadline.

### 15. How did I prove that the safety net works?

1. Instead of testing only a few examples, I tested every possible combination of hour, priority, time remaining, and number of reminders already sent.
2. There are 24 hours, 4 priorities, 96 possible half-hour deadline values, and 10 possible sent-today values.
3. Therefore, the safety tests cover \(24 \times 4 \times 96 \times 10 = 92,160\) possible situations.
4. The tests check that there is always at least one allowed action, the learner never waits past the deadline, urgent reminders are sent immediately, quiet hours are respected, and the daily limit is respected.
5. All of these situations passed the safety tests.
6. This gives stronger evidence than testing only a small number of examples because every possible situation in the defined range was checked.

### 16. How did I make the Q-learning agent respect the safety net?

1. The `choose()` function now receives a list of allowed actions from the safety net.
2. When the agent explores, it chooses randomly only from the allowed actions.
3. When the agent exploits its learned Q-values, it chooses the highest-scoring action only from the allowed actions.
4. The `learn()` function also receives the allowed actions for the next state.
5. Therefore, when calculating the future value, the learner only considers actions that will actually be allowed by the safety net.
6. This prevents the learner from planning around an action that the safety net would block later.

### 17. Why is the safety net important for my system?

1. A Q-learning model learns from rewards and does not automatically understand safety or user comfort.
2. A high reward could sometimes encourage an unsafe decision, such as sending a reminder during quiet hours.
3. The safety net provides fixed safety guarantees independently of what the model learns.
4. In my experiments, the safety net reduced both missed deadlines and rule breaks to zero.
5. Therefore, the system does not depend only on the learner behaving correctly; important safety rules are enforced separately.

### 18. What is the cold-start problem?

1. The cold-start problem happens when a brand-new user has no previous reminder history.
2. A personalised Q-learning model trained only on that user has no data to learn from at the beginning.
3. This can make the system perform poorly during the first few reminders.
4. To solve this, I trained one shared model using all the pretend users.
5. This shared model can then be used as a head start for a new user.
6. The new user's own data can then gradually personalise the shared model.

### 19. What did I learn from training one model for everyone?

1. A shared model can learn general reminder-timing patterns from several users.
2. However, one model cannot perfectly represent every person's behaviour because different users have different response patterns.
3. For example, the shared model performed well for users who preferred later times, but it did not provide the same benefit for the morning person.
4. This shows that a single model is useful as a starting point, but personalisation is still important.
5. Therefore, my system should use a shared model to give a new user a useful starting point and then continue learning from that user's own behaviour.

### 20. What is the head-start experiment?

1. I compared two ways of training a brand-new user: starting the Q-table from zero and starting from a model trained on the other users.
2. The head-start model was trained using all users except the new user.
3. The new user's own reminders were then used to personalise both models.
4. I tested different amounts of practice: 0, 1,000, 2,000, 5,000, 10,000, and 20,000 reminders.
5. I repeated the experiment using 3 different seeds and averaged the results.
6. This allowed me to investigate whether knowledge from other users can help during the cold-start period.

### 21. What did I learn from the night-owl head-start experiment?

1. For `night_owl_student`, the head-start model was better at the beginning of learning.
2. In my experiment, at 0 practice reminders the head-start model reached 0.36, while the from-zero model reached 0.24.
3. At 1,000 reminders, the head-start model reached 0.38, compared with 0.34 from zero.
4. At 2,000 reminders, the two approaches were approximately equal.
5. At 20,000 reminders, the from-zero model reached 0.50, while the head-start model reached 0.47.
6. This suggests that the head start is most useful during the early cold-start period, while enough personal data eventually allows a model trained from zero to learn the user's behaviour well.
7. The small differences in the later results should not be treated as a strong disadvantage because they can also be affected by random variation between runs.

### 22. Why did I test a different new user?

1. I changed the new user from `night_owl_student` to `morning_person` to see whether the head-start model works equally well for a different type of user.
2. I predicted that the head start would help the morning person less than the night owl because the shared model is influenced by the habits of the other users.
3. The morning person already has a relatively good result with the send-when-due strategy, so there is less room for the shared model to provide an improvement.
4. This experiment helps show that the usefulness of a shared model depends on how similar the new user's behaviour is to the users used to train it.
5. After the experiment, I changed `NEW_USER` back to `night_owl_student` so the saved thesis experiment represents the intended final configuration.

### 23. What are the five methods in my fair race?

1. Send when due: Sends the reminder as soon as it is due. This is my original rule-based baseline.
2. Random timing: Randomly chooses one of the allowed actions.
3. Mornings only: Tries to send reminders during the morning and waits at other times when possible.
4. Learner, no planning: Uses Q-learning with \(\gamma = 0\), so it does not consider future rewards.
5. Q-learner: Uses the normal Q-learning model with \(\gamma = 0.95\), allowing it to consider future rewards and plan ahead.
6. Comparing these methods allows me to measure whether my Q-learning approach provides an advantage over simpler strategies.

### 24. How did I make the fair race fair?

1. Every method uses the safety net.
2. Every method is tested using fresh reminders that were not used during training.
3. The methods receive the same test situations so that one method does not get easier reminders than another.
4. The learners are trained using 3 different random seeds.
5. The results from the 3 runs are averaged to reduce the effect of one lucky or unlucky run.
6. The experiment records response rate, average points, missed deadlines, and rule breaks.
7. The raw results are saved in `race.csv`, while the comparison chart is saved in `race.png`.

### 25. What were the overall results of the fair race?

1. The Q-learner performed best. My learner achieved an average response rate of 0.46, compared with 0.24 for send when due.
2. The learner also achieved the highest average points at 0.28, compared with -0.03 for send when due.
3. The learner performed better than random timing and the mornings-only strategy.
4. The learner without planning achieved a response rate of 0.37, while the normal learner achieved 0.46.
5. Since the main difference between these two learners is the discount factor \(\gamma\), the 0.09 improvement provides evidence that looking ahead helps the reminder timing decision.
6. All five methods achieved 0.00 missed deadlines and 0.00 rule breaks because the safety net was active during the race.

### 26. What did I learn from my own pretend user?

1. My pretend user is `lunch_break_person`.
2. This user has a strong response peak around midday, between 12:00 and 14:00, with a response probability of about 0.9.
3. Outside this period, the response probability is much lower, so sending reminders at other times is less effective.
4. My learner achieved a response rate of 0.63 for this user.
5. This was much higher than 0.18 for send when due, 0.22 for mornings only, and 0.54 for the no-planning learner.
6. The learner performed well because it learned to wait for the user's strong midday response period instead of simply sending reminders when they became due.
7. The no-planning learner already achieved 0.54, which shows that learning the user's habit was responsible for most of the improvement. Planning ahead provided a further improvement of about 0.09.
8. This result shows that my Q-learning system can learn a specific user's behaviour rather than using the same fixed timing rule for everyone.

### 27. What are the main findings from my experiments?

1. The Q-learner wins: My learner achieved a mean response rate of 0.46, compared with 0.24 for send when due. It also achieved the highest average points.
2. The system is safe: The safety net resulted in 0.00 missed deadlines and 0.00 rule breaks across the race experiments.
3. Planning ahead matters: The no-planning learner achieved 0.37, while the normal Q-learner achieved 0.46. The difference of 0.09 shows the benefit of considering future rewards.
4. Fixed rules only suit some users: Mornings only performed almost as well as the learner for `morning_person` (0.59 vs 0.60) and reasonably well for `nine_to_five` (0.38 vs 0.40). However, it performed poorly for `evening_person` (0.23) and `night_owl_student` (0.20), while the learner achieved 0.61 and 0.55 respectively.
5. The learner does not invent patterns: For `busy_person`, the methods were all around 0.12–0.15, and for `no_pattern` they were around 0.30–0.33. This shows that when there is little useful behaviour to learn, the learner does not create a large artificial improvement.

### 28. What does the safety net guarantee?

1. The safety net guarantees that the learner cannot choose an action that violates the four safety rules.
2. I tested all 92,160 possible combinations of hour, priority, time remaining, and reminders sent today.
3. The tests verified that the learner always has at least one allowed action, never waits beyond the deadline, sends urgent reminders when necessary, respects quiet hours, and respects the daily limit.
4. In the race, every method had 0.00 missed deadlines and 0.00 rule breaks.
5. The safety net has a small performance cost. In the morning-person check, the learner's response rate decreased from 0.60 without the safety net to 0.59 with it.
6. Therefore, the safety net provides strong safety guarantees while causing only a small reduction in response performance.