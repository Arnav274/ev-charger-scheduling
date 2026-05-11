import pytest

from app.queueing import erlang_c_probability_of_delay, erlang_c_wait_minutes


def test_erlang_c_probability_bounds() -> None:
    p = erlang_c_probability_of_delay(arrival_rate_per_hour=4, service_rate_per_hour=1.5, c=4)
    assert 0 <= p <= 1


def test_erlang_c_wait_positive() -> None:
    wait = erlang_c_wait_minutes(arrival_rate_per_hour=6, mean_service_minutes=40, c=5)
    assert wait >= 0


def test_unstable_queue_penalty() -> None:
    wait = erlang_c_wait_minutes(arrival_rate_per_hour=100, mean_service_minutes=40, c=2)
    assert wait == 1e6


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        erlang_c_probability_of_delay(-1, 1.0, 2)
