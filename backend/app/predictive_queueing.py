from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class ReservationInterval:
    """Lightweight projection of a Reservation row, used by the sweep-line overlap counter."""
    start_time: datetime
    end_time: datetime




def ensure_utc(dt: datetime) -> datetime:
    """Normalise to UTC. Naive datetimes are assumed UTC; aware datetimes are converted."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)




def arrival_window(
    *,
    departure_time: datetime,
    travel_time_min: float,
    arrival_window_minutes: int,
) -> tuple[datetime, datetime, datetime]:
    """
    Return (arrival_est, window_start, window_end).

    The window [arrival_est, arrival_est + arrival_window_minutes) is used to
    query which reservations overlap the user's expected arrival, so algorithms
    can estimate how many chargers will actually be free when they get there.
    """
    departure_time = ensure_utc(departure_time)
    arrival_est = departure_time + timedelta(minutes=float(travel_time_min))
    window_start = arrival_est
    window_end = arrival_est + timedelta(minutes=int(arrival_window_minutes))
    return arrival_est, window_start, window_end




def max_overlapping(intervals: list[ReservationInterval]) -> int:
    """
    Maximum number of overlapping intervals at any moment.
    """
    events: list[tuple[datetime, int]] = []
    for it in intervals:
        s = ensure_utc(it.start_time)
        e = ensure_utc(it.end_time)
        if e <= s:
            continue
        events.append((s, +1))
        events.append((e, -1))
    if not events:
        return 0

    # Sweep-line: sort events by time, breaking ties so -1 (end) sorts before
    # +1 (start) at the same instant — avoids counting a departing and arriving
    # car simultaneously as two occupied chargers.
    events.sort(key=lambda x: (x[0], x[1]))
    current = 0
    best = 0
    for _t, delta in events:
        current += delta
        if current > best:
            best = current
    return best



def count_starts_in_window(
    intervals: list[ReservationInterval], *, window_start: datetime, window_end: datetime
) -> int:
    window_start = ensure_utc(window_start)
    window_end = ensure_utc(window_end)
    if window_end <= window_start:
        return 0
    return sum(1 for it in intervals if window_start <= ensure_utc(it.start_time) < window_end)

