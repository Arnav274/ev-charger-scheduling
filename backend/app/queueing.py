import math


def erlang_c_probability_of_delay(arrival_rate_per_hour: float, service_rate_per_hour: float, c: int) -> float:
    """
    Return Erlang-C probability of delay P(W>0) for an M/M/c queue.
    """
    if c <= 0:
        raise ValueError("c must be >= 1")
    if arrival_rate_per_hour < 0 or service_rate_per_hour <= 0:
        raise ValueError("arrival/service rates must be positive")

    rho = arrival_rate_per_hour / (c * service_rate_per_hour)
    if rho >= 1:
        return 1.0

    c_rho = arrival_rate_per_hour / service_rate_per_hour
    series = sum((c_rho**k) / math.factorial(k) for k in range(c))
    tail = (c_rho**c) / math.factorial(c) * (1 / (1 - rho))
    return tail / (series + tail)


def erlang_c_wait_minutes(arrival_rate_per_hour: float, mean_service_minutes: float, c: int) -> float:
    """
    Expected waiting time Wq in minutes.
    """
    if mean_service_minutes <= 0:
        raise ValueError("mean_service_minutes must be > 0")

    service_rate_per_hour = 60.0 / mean_service_minutes
    rho = arrival_rate_per_hour / (c * service_rate_per_hour)
    if rho >= 1:
        return 1e6

    pw = erlang_c_probability_of_delay(arrival_rate_per_hour, service_rate_per_hour, c)
    wq_hours = pw / (c * service_rate_per_hour * (1 - rho))
    return wq_hours * 60.0
