from datetime import UTC, datetime, timedelta, timezone

from app.predictive_queueing import ReservationInterval, booked_during_arrival, ensure_utc, max_overlapping

T0 = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)


def interval(start_min: int, end_min: int) -> ReservationInterval:
    return ReservationInterval(T0 + timedelta(minutes=start_min), T0 + timedelta(minutes=end_min))


def test_nested_intervals_all_overlap() -> None:
    assert max_overlapping([interval(0, 10), interval(1, 9), interval(2, 3)]) == 3


def test_touching_intervals_do_not_overlap() -> None:
    assert max_overlapping([interval(0, 10), interval(10, 20), interval(20, 30)]) == 1


def test_peak_is_the_maximum_not_the_total() -> None:
    intervals = [interval(0, 10), interval(5, 15), interval(20, 30), interval(22, 28), interval(24, 26)]
    assert max_overlapping(intervals) == 3


def test_empty_and_degenerate_intervals() -> None:
    assert max_overlapping([]) == 0
    assert max_overlapping([interval(5, 5), interval(9, 3)]) == 0


def test_mixed_timezones_are_compared_in_utc() -> None:
    bst = timezone(timedelta(hours=1))
    start = datetime(2030, 1, 1, 10, 30, tzinfo=bst)
    a = ReservationInterval(T0, T0 + timedelta(hours=1))
    # 10:30-11:30 BST is 09:30-10:30 UTC, which overlaps a.
    b = ReservationInterval(start, start + timedelta(hours=1))
    assert max_overlapping([a, b]) == 2


def test_ensure_utc() -> None:
    naive = datetime(2030, 1, 1, 12, 0)
    assert ensure_utc(naive) == datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    bst = datetime(2030, 6, 1, 13, 0, tzinfo=timezone(timedelta(hours=1)))
    assert ensure_utc(bst).hour == 12


def test_booked_during_arrival_only_counts_the_window() -> None:
    bookings = [interval(0, 30), interval(10, 40), interval(60, 90)]
    window = timedelta(minutes=15)
    assert booked_during_arrival(bookings, T0 + timedelta(minutes=12), window) == 2
    assert booked_during_arrival(bookings, T0 + timedelta(minutes=45), window) == 0
    assert booked_during_arrival(bookings, T0 + timedelta(minutes=50), window) == 1
