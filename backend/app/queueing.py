"""Erlang-C (M/M/c) queueing formulae for predicting wait time at charging stations.

A station with c chargers is modelled as an M/M/c queue: Poisson arrivals at
rate λ per hour, exponentially distributed charging sessions with mean 1/μ,
and c identical servers. The offered load is a = λ/μ and the per-charger
utilisation is ρ = a/c.
"""

from dataclasses import dataclass
from functools import lru_cache

# When ρ >= 1 arrivals outpace service and the expected wait is unbounded. We
# report a finite ceiling instead: four hours is long enough that no driver
# would choose the station, and keeping it finite means a single saturated
# station cannot swamp the normalisation that the scoring strategies rely on.
SATURATED_WAIT_MINUTES = 240.0


@dataclass(frozen=True)
class WaitPrediction:
    wait_min: float
    probability_of_delay: float


def erlang_c_probability_of_delay(
    arrival_rate_per_hour: float, service_rate_per_hour: float, c: int
) -> float:
    """Probability that an arriving customer has to queue, P(W > 0).

    Computed through the Erlang-B recursion B(k) = a·B(k-1) / (k + a·B(k-1)),
    then C = c·B / (c - a·(1 - B)). This avoids the factorials in the textbook
    form, which overflow for large c.
    """
    if c <= 0:
        raise ValueError("c must be >= 1")
    if arrival_rate_per_hour < 0 or service_rate_per_hour <= 0:
        raise ValueError("arrival rate must be >= 0 and service rate > 0")

    offered_load = arrival_rate_per_hour / service_rate_per_hour
    if offered_load >= c:
        return 1.0

    erlang_b = 1.0
    for k in range(1, c + 1):
        erlang_b = offered_load * erlang_b / (k + offered_load * erlang_b)
    return c * erlang_b / (c - offered_load * (1 - erlang_b))


def erlang_c_wait_minutes(arrival_rate_per_hour: float, mean_service_minutes: float, c: int) -> float:
    """Expected time spent queueing before a charger frees up, Wq, in minutes.

    Wq = C / (c·μ - λ). Saturated queues return SATURATED_WAIT_MINUTES, and so
    does any finite wait longer than that ceiling.
    """
    if mean_service_minutes <= 0:
        raise ValueError("mean_service_minutes must be > 0")

    service_rate_per_hour = 60.0 / mean_service_minutes
    capacity = c * service_rate_per_hour
    if arrival_rate_per_hour >= capacity:
        return SATURATED_WAIT_MINUTES

    p_delay = erlang_c_probability_of_delay(arrival_rate_per_hour, service_rate_per_hour, c)
    wait_hours = p_delay / (capacity - arrival_rate_per_hour)
    return min(wait_hours * 60.0, SATURATED_WAIT_MINUTES)


@lru_cache(maxsize=4096)
def predict_wait(arrival_rate_per_hour: float, mean_service_minutes: float, chargers: int) -> WaitPrediction:
    """Expected wait and probability of waiting for a station with `chargers` free chargers.

    Cached: stations share a handful of parameter combinations, and ranking
    calls this once per candidate station for every request.
    """
    chargers = max(1, chargers)
    return WaitPrediction(
        wait_min=erlang_c_wait_minutes(arrival_rate_per_hour, mean_service_minutes, chargers),
        probability_of_delay=erlang_c_probability_of_delay(
            arrival_rate_per_hour, 60.0 / mean_service_minutes, chargers
        ),
    )
