"""Reservation lookahead: how many chargers are already booked when a driver arrives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ReservationInterval:
    start_time: datetime
    end_time: datetime


def ensure_utc(dt: datetime) -> datetime:
    """Normalise to UTC. Naive datetimes are assumed to already be UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def max_overlapping(intervals: Iterable[ReservationInterval]) -> int:
    """Largest number of intervals in progress at the same instant (sweep line, O(n log n)).

    Intervals are half-open, so one booking ending at 10:00 and another starting
    at 10:00 never count as overlapping. Callers pass only the bookings that
    intersect the driver's arrival window; for intervals on a line, any group
    that pairwise overlaps shares a common instant, so this peak always falls
    inside that window.
    """
    events: list[tuple[datetime, int]] = []
    for it in intervals:
        start, end = ensure_utc(it.start_time), ensure_utc(it.end_time)
        if end > start:
            events.append((start, +1))
            events.append((end, -1))

    # At equal timestamps -1 sorts before +1, so an end is processed before a start.
    events.sort()
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak
