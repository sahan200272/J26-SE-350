from app.simulation import PretendUser, day_part

ENGAGED = {"opened", "done", "snoozed"}


def engaged_rate(user, hour, tries=2000, sent_today=0):
    answers = [user.respond(hour, False, "normal", sent_today) for _ in range(tries)]
    return sum(a in ENGAGED for a in answers) / tries


def test_day_part():
    assert day_part(3) == "night"
    assert day_part(8) == "early"
    assert day_part(10) == "morning"
    assert day_part(13) == "midday"
    assert day_part(15) == "afternoon"
    assert day_part(21) == "evening"


def test_morning_person_prefers_mornings():
    user = PretendUser("morning_person", seed=1)
    assert engaged_rate(user, hour=10) > engaged_rate(user, hour=15)


def test_tiredness_lowers_the_chance():
    user = PretendUser("morning_person")
    fresh = user.chance_of_response(10, False, sent_today=0)
    tired = user.chance_of_response(10, False, sent_today=8)
    assert tired < fresh


def test_same_seed_gives_same_answers():
    a = PretendUser("no_pattern", seed=42)
    b = PretendUser("no_pattern", seed=42)
    answers_a = [a.respond(10, False, "high", 0) for _ in range(50)]
    answers_b = [b.respond(10, False, "high", 0) for _ in range(50)]
    assert answers_a == answers_b