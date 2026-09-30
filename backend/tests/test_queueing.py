"""Erlang-C checked against closed forms and published values."""

import math

import pytest

from app.queueing import (
    SATURATED_WAIT_MINUTES,
    erlang_c_probability_of_delay,
    erlang_c_wait_minutes,
    predict_wait,
)


def textbook_erlang_c(a: float, c: int) -> float:
    """The factorial form, used as an independent reference for small c."""
    top = a**c / math.factorial(c) * c / (c - a)
    return top / (sum(a**k / math.factorial(k) for k in range(c)) + top)


@pytest.mark.parametrize("lam,mu", [(0.5, 1.5), (1.0, 2.0), (2.0, 3.0)])
def test_single_server_reduces_to_mm1(lam: float, mu: float) -> None:
    rho = lam / mu
    # M/M/1: P(wait) = ρ and Wq = ρ / (μ - λ).
    assert erlang_c_probability_of_delay(lam, mu, 1) == pytest.approx(rho)
    assert erlang_c_wait_minutes(lam, 60 / mu, 1) == pytest.approx(rho / (mu - lam) * 60)


def test_default_station_parameters() -> None:
    # λ = 0.75/h, 40 min sessions: one charger gives ρ = 0.5 and Wq = 40 min;
    # a second charger cuts the wait to 8/3 min.
    assert erlang_c_wait_minutes(0.75, 40, 1) == pytest.approx(40.0)
    assert erlang_c_wait_minutes(0.75, 40, 2) == pytest.approx(8 / 3)


def test_published_call_centre_example() -> None:
    # 10 Erlangs offered to 12 agents: P(wait) ≈ 0.4494, a standard worked example.
    assert erlang_c_probability_of_delay(10.0, 1.0, 12) == pytest.approx(0.4494, abs=1e-4)


@pytest.mark.parametrize("a,c", [(0.3, 1), (1.7, 3), (4.2, 6), (9.5, 12)])
def test_recursion_matches_the_factorial_form(a: float, c: int) -> None:
    assert erlang_c_probability_of_delay(a, 1.0, c) == pytest.approx(textbook_erlang_c(a, c))


def test_large_server_counts_do_not_overflow() -> None:
    # The factorial form overflows a float well before c = 400.
    p = erlang_c_probability_of_delay(380.0, 1.0, 400)
    assert 0 < p < 1


def test_more_chargers_never_increase_the_wait() -> None:
    waits = [erlang_c_wait_minutes(2.0, 40, c) for c in range(2, 10)]
    assert waits == sorted(waits, reverse=True)


def test_saturated_queue_is_capped() -> None:
    assert erlang_c_probability_of_delay(3.0, 1.5, 2) == 1.0
    assert erlang_c_wait_minutes(3.0, 40, 2) == SATURATED_WAIT_MINUTES
    assert erlang_c_wait_minutes(100, 40, 2) == SATURATED_WAIT_MINUTES


def test_very_long_finite_waits_are_capped_too() -> None:
    # ρ = 0.999 on one charger is finite but around 11 days of queueing.
    assert erlang_c_wait_minutes(1.4985, 40, 1) == SATURATED_WAIT_MINUTES


def test_no_arrivals_means_no_wait() -> None:
    assert erlang_c_wait_minutes(0.0, 40, 2) == 0.0


def test_predict_wait_bundles_both_measures() -> None:
    prediction = predict_wait(0.75, 40, 1)
    assert prediction.wait_min == pytest.approx(40.0)
    assert prediction.probability_of_delay == pytest.approx(0.5)
    assert predict_wait(0.75, 40, 0) == prediction  # zero chargers is treated as one


@pytest.mark.parametrize(
    "args",
    [(-1.0, 1.0, 2), (1.0, 0.0, 2), (1.0, 1.0, 0)],
)
def test_invalid_inputs(args) -> None:
    with pytest.raises(ValueError):
        erlang_c_probability_of_delay(*args)
    with pytest.raises(ValueError):
        erlang_c_wait_minutes(1.0, 0.0, 1)
