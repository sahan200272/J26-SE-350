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
 
 
# def evaluate(env, choose, episodes=5000, use_shield=False): 
#     """Measure a way of choosing over many reminders, without learning.""" 
#     points, engaged, missed, rule_breaks = 0.0, 0, 0, 0 
#     for _ in range(episodes): 
#         state = env.reset() 
#         while True: 
#             action = choose(state, moves_for(env, use_shield)) 
#             if action == SEND_NOW and SEND_NOW not in allowed_for(env): 
#                 rule_breaks += 1          # a send the safety net would have blocked 
#             state, reward, finished, outcome = env.step(action) 
#             points += reward 
#             if finished: 
#                 engaged += outcome in ENGAGED 
#                 missed += outcome == "missed" 
#                 break 
#     return {"average points": points / episodes, 
#             "response rate": engaged / episodes, 
#             "missed deadlines": missed / episodes, 
#             "rule breaks": rule_breaks / episodes} 
def best_chance_before_deadline(env):
    """Find the best response chance available before the deadline."""

    best = 0.0

    for step in range(0, env.minutes_left + 1, 30):
        future_minute = env.minute + step
        future_day = env.day

        # Move through future days if the look-ahead crosses midnight.
        extra_days = future_minute // (24 * 60)
        future_day = (future_day + extra_days) % 7

        future_minute = future_minute % (24 * 60)

        future_hour = future_minute // 60
        future_weekend = future_day >= 5

        chance = env.user.chance_of_response(
            future_hour,
            future_weekend,
            env.sent_today
        )

        best = max(best, chance)

    return best


def evaluate(env, choose, episodes=5000, use_shield=False):
    """Measure a policy over many reminders, without learning."""

    points = 0.0
    engaged = 0
    missed = 0
    rule_breaks = 0

    # Timing metrics
    timing_ratios = []
    good_timing = 0

    # Interruption metrics
    high_fatigue_sends = 0
    total_sends = 0
    negative_responses = 0
    total_holds = 0

    for _ in range(episodes):
        state = env.reset()

        while True:
            allowed = moves_for(env, use_shield)

            action = choose(state, allowed)

            # Check whether this send would have been blocked
            # by the safety shield.
            if action == SEND_NOW and SEND_NOW not in allowed_for(env):
                rule_breaks += 1

            # -----------------------------
            # Timing accuracy
            # -----------------------------
            if action == SEND_NOW:
                chosen_chance = env.user.chance_of_response(
                    env.hour(),
                    env.is_weekend(),
                    env.sent_today
                )

                best_chance = best_chance_before_deadline(env)

                timing_ratio = (
                    chosen_chance / max(best_chance, 1e-9)
                )

                timing_ratios.append(timing_ratio)

                if timing_ratio >= 0.8:
                    good_timing += 1

                # Interruption burden
                total_sends += 1

                if env.sent_today >= 3:
                    high_fatigue_sends += 1

            else:
                # The policy chose to wait.
                total_holds += 1

            state, reward, finished, outcome = env.step(action)

            points += reward

            if finished:
                # Engagement
                if outcome in ENGAGED:
                    engaged += 1

                # Missed deadline
                if outcome == "missed":
                    missed += 1

                # Negative response
                if outcome in {"dismissed", "snoozed"}:
                    negative_responses += 1

                break

    # -----------------------------
    # Alert precision
    # -----------------------------
    precision = engaged / episodes

    # -----------------------------
    # Alert recall
    # -----------------------------
    recall = 1 - (missed / episodes)

    # -----------------------------
    # F1
    # -----------------------------
    if precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0.0

    # -----------------------------
    # Timing accuracy
    # -----------------------------
    if timing_ratios:
        mean_timing_ratio = (
            sum(timing_ratios) / len(timing_ratios)
        )

        timing_accuracy = (
            good_timing / len(timing_ratios)
        )
    else:
        mean_timing_ratio = 0.0
        timing_accuracy = 0.0

    # -----------------------------
    # Interruption burden
    # -----------------------------
    if total_sends > 0:
        high_fatigue_rate = (
            high_fatigue_sends / total_sends
        )

        negative_response_rate = (
            negative_responses / total_sends
        )
    else:
        high_fatigue_rate = 0.0
        negative_response_rate = 0.0

    return {
        # Existing metrics
        "average points": points / episodes,
        "response rate": precision,
        "missed deadlines": missed / episodes,
        "rule breaks": rule_breaks / episodes,

        # New alert metrics
        "alert precision": precision,
        "alert recall": recall,
        "alert F1": f1,

        # Timing metrics
        "mean timing ratio": mean_timing_ratio,
        "timing accuracy": timing_accuracy,

        # Interruption metrics
        "notifications per task": total_sends / episodes,
        "high fatigue send rate": high_fatigue_rate,
        "negative response rate": negative_response_rate,
        "average holds": total_holds / episodes,
    }
 
 
def always_send_now(state, allowed=ALL_MOVES): 
    """Baseline: send as soon as it's allowed (original rule-based system).""" 
    return SEND_NOW if SEND_NOW in allowed else WAIT_30
