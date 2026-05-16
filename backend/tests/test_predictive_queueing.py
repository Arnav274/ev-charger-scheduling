from datetime import datetime, timedelta, timezone

from app.predictive_queueing import ReservationInterval, count_starts_in_window, max_overlapping


def test_max_overlapping_counts_concurrency() -> None:
    now = datetime.now(timezone.utc)
    intervals = [
        ReservationInterval(now, now + timedelta(minutes=10)),
        ReservationInterval(now + timedelta(minutes=1), now + timedelta(minutes=9)),
        ReservationInterval(now + timedelta(minutes=2), now + timedelta(minutes=3)),
    ]
    assert max_overlapping(intervals) == 3


def test_count_starts_in_window() -> None:
    now = datetime.now(timezone.utc)
    intervals = [
        ReservationInterval(now + timedelta(minutes=1), now + timedelta(minutes=2)),
        ReservationInterval(now + timedelta(minutes=5), now + timedelta(minutes=20)),
        ReservationInterval(now + timedelta(minutes=25), now + timedelta(minutes=30)),
    ]
    assert (
        count_starts_in_window(intervals, window_start=now, window_end=now + timedelta(minutes=21))
        == 2
    )

