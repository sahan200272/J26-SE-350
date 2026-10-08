"""Pretend users for training and testing the notification timing model."""
import random

# The six parts of the day used everywhere in the project.
DAY_PARTS = ["night", "early", "morning", "midday", "afternoon", "evening"]


def day_part(hour):
    """Turn an hour (0-23) into one of the six parts of the day."""
    if hour < 6:
        return "night"
    if hour < 9:
        return "early"
    if hour < 12:
        return "morning"
    if hour < 14:
        return "midday"
    if hour < 18:
        return "afternoon"
    return "evening"


# Each pretend user: the chance (0 to 1) they respond in each part of a weekday,
# and how much that chance changes at the weekend (1.0 = no change).
PERSONAS = {
    "morning_person": {
        "chances": {"night": 0.02, "early": 0.5, "morning": 0.8,
                    "midday": 0.4, "afternoon": 0.3, "evening": 0.3},
        "weekend_factor": 0.8,
    },
    "evening_person": {
        "chances": {"night": 0.05, "early": 0.1, "morning": 0.25,
                    "midday": 0.35, "afternoon": 0.45, "evening": 0.8},
        "weekend_factor": 1.0,
    },
    "lunch_break_person": {
            "chances": {"night": 0.02, "early": 0.1, "morning": 0.3,
                        "midday": 0.9, "afternoon": 0.35, "evening": 0.2},
            "weekend_factor": 0.8,
    },
    "nine_to_five": {
        "chances": {"night": 0.02, "early": 0.3, "morning": 0.6,
                    "midday": 0.5, "afternoon": 0.6, "evening": 0.2},
        "weekend_factor": 0.3,
    },
    "night_owl_student": {
        "chances": {"night": 0.3, "early": 0.05, "morning": 0.2,
                    "midday": 0.4, "afternoon": 0.5, "evening": 0.7},
        "weekend_factor": 1.0,
    },
    "busy_person": {
        "chances": {"night": 0.02, "early": 0.15, "morning": 0.2,
                    "midday": 0.15, "afternoon": 0.2, "evening": 0.15},
        "weekend_factor": 0.7,
    },
    "no_pattern": {
        "chances": {"night": 0.35, "early": 0.35, "morning": 0.35,
                    "midday": 0.35, "afternoon": 0.35, "evening": 0.35},
        "weekend_factor": 1.0,
    },
}

# If the user does engage, how likely they are to mark the task done straight away.
DONE_CHANCE = {"critical": 0.5, "high": 0.4, "normal": 0.3, "low": 0.2}


class PretendUser:
    """A simulated person who reacts to notifications."""

    def __init__(self, persona_name, seed=None):
        self.name = persona_name
        self.profile = PERSONAS[persona_name]
        self.rng = random.Random(seed)  # its own dice, so results can be repeated

    def chance_of_response(self, hour, is_weekend, sent_today):
        """How likely this person is to engage with a notification right now."""
        chance = self.profile["chances"][day_part(hour)]
        if is_weekend:
            chance = chance * self.profile["weekend_factor"]
        # Tiredness: every notification after the third today makes a response less likely.
        extra = max(0, sent_today - 3)
        chance = chance * (0.85 ** extra)
        return min(chance, 1.0)

    def respond(self, hour, is_weekend, priority, sent_today):
        """Roll the dice and return what the person does with one notification."""
        if self.rng.random() >= self.chance_of_response(hour, is_weekend, sent_today):
            # Did not engage: usually just ignores it, sometimes swipes it away.
            return "dismissed" if self.rng.random() < 0.3 else "ignored"
        roll = self.rng.random()
        if roll < DONE_CHANCE[priority]:
            return "done"
        if roll < DONE_CHANCE[priority] + 0.15:
            return "snoozed"
        return "opened"