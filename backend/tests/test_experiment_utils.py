from experiments.run_experiments import jain_fairness, overlaps, try_reserve


def test_jain_fairness_bounds() -> None:
    assert 0 <= jain_fairness([1, 1, 1, 1]) <= 1
    assert jain_fairness([1, 1, 1, 1]) > jain_fairness([4, 0, 0, 0])


def test_overlaps_logic() -> None:
    assert overlaps(10, 20, 15, 25)
    assert not overlaps(10, 20, 20, 30)


def test_try_reserve_blocks_fully_overlapping_slots() -> None:
    schedules = {"a": [(10, 20)], "b": [(10, 20)]}
    assert not try_reserve(schedules, request_start_min=12, duration_min=5)
    assert try_reserve(schedules, request_start_min=20, duration_min=5)
