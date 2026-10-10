
"""One reminder, from the moment it is due until it is sent or the deadline passes."""

import random

from app.state import PRIORITIES, encode_state

SEND_NOW, WAIT_30, WAIT_2H = 0, 1, 2

ACTION_NAMES = [
    "send now", 
    "wait 30 min", 
    "wait 2 h"
]

# Points the learner gets for each outcome.
REWARDS = {
    "done": 2.0,
    "opened": 1.0,
    "ignored": 0.0,
    "snoozed": -0.5,
    "dismissed": -1.0,
}

WAIT_COST = -0.01          # a tiny cost for every wait, so it doesn't wait forever
MISSED_PENALTY = -3.0      # the deadline passed and no reminder was ever sent


class ReminderEnv:
    """The practice world: one pretend user, one reminder at a time."""

    def __init__(self, user, seed=None):
        self.user = user
        self.rng = random.Random(seed)

    def reset(self):
        """Start a new reminder at a random moment. Returns the starting situation."""
        self.day = self.rng.randint(0, 6)                             # 0 = Monday ... 6 = Sunday
        self.minute = self.rng.randrange(0, 24 * 60, 30)              # time of day, in minutes
        self.priority = self.rng.choice(PRIORITIES)
        self.minutes_left = self.rng.randrange(2 * 60, 48 * 60 + 1, 30)
        self.sent_today = self.rng.randint(0, 8)
        return self.state()

    def hour(self):
        return self.minute // 60

    def is_weekend(self):
        return self.day >= 5

    def state(self):
        return encode_state(
            self.hour(),
            self.is_weekend(),
            self.priority,
            self.minutes_left,
            self.sent_today,
        )

    def step(self, action):
        """Do one action. Returns (next situation, points, finished?, what happened)."""
        if action == SEND_NOW:
            response = self.user.respond(
                self.hour(),
                self.is_weekend(),
                self.priority,
                self.sent_today,
            )
            return self.state(), REWARDS[response], True, response

        wait = 30 if action == WAIT_30 else 120 
        self.minutes_left -= wait 
        self.minute += wait 
        if self.minute >= 24 * 60:              # past midnight: next day 
            self.minute -= 24 * 60 
            self.day = (self.day + 1) % 7 
            self.sent_today = 0                 # a new day starts with no reminders sent 
        if self.minutes_left <= 0: 
            return self.state(), MISSED_PENALTY, True, "missed" 
        return self.state(), WAIT_COST, False, "waiting"