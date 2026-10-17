from app.state import N_STATES, encode_state, sent_bucket, time_left_bucket


def test_buckets():
    assert time_left_bucket(30) == 0
    assert time_left_bucket(3 * 60) == 1
    assert time_left_bucket(30 * 60) == 3

    assert sent_bucket(0) == 0
    assert sent_bucket(4) == 1
    assert sent_bucket(9) == 2


def test_every_situation_gets_its_own_number():
    numbers = set()

    for hour in [3, 7, 10, 13, 15, 20]:
        for weekend in [False, True]:
            for priority in ["critical", "high", "normal", "low"]:
                for minutes in [
                    30,
                    3 * 60,
                    12 * 60,
                    36 * 60,
                    60 * 60,
                ]:
                    for sent in [0, 4, 7]:
                        numbers.add(
                            encode_state(
                                hour,
                                weekend,
                                priority,
                                minutes,
                                sent,
                            )
                        )

    assert len(numbers) == N_STATES == 720
    assert min(numbers) == 0 and max(numbers) == 719