"""Turn a moment into a single situation number (a row in the Q-table)."""
from app.simulation import DAY_PARTS, day_part


PRIORITIES = [
    "critical", 
    "high", 
    "normal", 
    "low",
]

TIME_LEFT_LABELS = [
    "under 1h",
    "1-6h",
    "6-24h",
    "24-48h",
    "over 48h",
]

SENT_LABELS = [
    "0-2 sent",
    "3-5 sent",
    "6+ sent",
]


N_STATES = (
    len(DAY_PARTS)
    * 2
    * len(PRIORITIES)
    * len(TIME_LEFT_LABELS)
    * len(SENT_LABELS)
)


def time_left_bucket(minutes_left):
    """Group the time until the deadline into 5 buckets."""
    hours = minutes_left / 60

    if hours < 1:
        return 0
    if hours < 6:
        return 1
    if hours < 24:
        return 2
    if hours < 48:
        return 3

    return 4


def sent_bucket(sent_today):
    """Group how many reminders were already sent today into 3 buckets."""
    if sent_today <= 2:
        return 0
    if sent_today <= 5:
        return 1

    return 2


def encode_state(hour, is_weekend, priority, minutes_left, sent_today):
    """Combine the five parts of a situation into one number from 0 to 719."""

    part = DAY_PARTS.index(day_part(hour))
    weekend = 1 if is_weekend else 0
    prio = PRIORITIES.index(priority)
    left = time_left_bucket(minutes_left)
    sent = sent_bucket(sent_today)

    return (((part * 2 + weekend) * 4 + prio) * 5 + left) * 3 + sent