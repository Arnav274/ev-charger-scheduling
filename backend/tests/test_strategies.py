"""Unit tests for each SelectionStrategy in app.algorithms."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.algorithms import (
    DijkstraStrategy,
    NearestStrategy,
    QueueAwareStrategy,
    RangeAwareStrategy,
    RecommendationContext,
    StaticQueueStrategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_station(
    lat: float,
    lon: float,
    *,
    num_chargers: int = 1,
    arrival_rate: float = 4.0,
    mean_service: float = 40.0,
) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.lat = lat
    s.lon = lon
    s.price_pence_per_kwh = 55.0
    s.arrival_rate_per_hour = arrival_rate
    s.mean_service_minutes = mean_service
    s.chargers = [MagicMock() for _ in range(num_chargers)]
    return s


def _ctx(origin_lat: float = 0.0, origin_lon: float = 0.0, **kwargs) -> RecommendationContext:
    return RecommendationContext(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        weights=(1 / 3, 1 / 3, 1 / 3),
        **kwargs,
    )


_MAX = {"distance": 100.0, "wait": 1000.0, "cost": 100.0}


# ---------------------------------------------------------------------------
# NearestStrategy
# ---------------------------------------------------------------------------

class TestNearestStrategy:
    def test_nearest_returns_closest_station(self):
        # At lat 51.5°, 0.009° ≈ 1 km, 0.018° ≈ 2 km, 0.045° ≈ 5 km.
        origin_lat, origin_lon = 51.5, -0.1
        s1 = _make_station(lat=origin_lat + 0.009, lon=origin_lon)
        s2 = _make_station(lat=origin_lat + 0.018, lon=origin_lon)
        s3 = _make_station(lat=origin_lat + 0.045, lon=origin_lon)

        strategy = NearestStrategy()
        ctx = _ctx(origin_lat, origin_lon)

        scores = {s.id: strategy.score(s, ctx, _MAX) for s in [s1, s2, s3]}
        ordered = sorted(scores, key=scores.get)
        assert ordered == [s1.id, s2.id, s3.id]


# ---------------------------------------------------------------------------
# QueueAwareStrategy
# ---------------------------------------------------------------------------

class TestQueueAwareStrategy:
    def test_queue_aware_higher_score_under_reservations(self):
        station = _make_station(
            lat=0.01, lon=0.0,
            num_chargers=2,
            arrival_rate=1.0,   # rho < 1 for both strategies so waits are finite
            mean_service=40.0,
        )
        ctx = _ctx(
            0.0, 0.0,
            future_reserved_parallel_by_station={str(station.id): 2},
            future_reservation_starts_by_station={str(station.id): 0},
            current_occupancy_by_station={str(station.id): 0},
        )

        score_qa = QueueAwareStrategy().score(station, ctx, _MAX)
        score_sq = StaticQueueStrategy().score(station, ctx, _MAX)

        assert score_qa > score_sq


# ---------------------------------------------------------------------------
# DijkstraStrategy
# ---------------------------------------------------------------------------

class TestDijkstraStrategy:
    def test_dijkstra_strategy_consistent_with_haversine(self):
        origin_lat, origin_lon = 0.0, 0.0
        s_near = _make_station(lat=0.01, lon=0.0)
        s_mid = _make_station(lat=0.05, lon=0.0)
        s_far = _make_station(lat=0.10, lon=0.0)
        stations = [s_near, s_mid, s_far]

        ctx = _ctx(origin_lat, origin_lon)

        def nearest_id(strategy):
            return min(stations, key=lambda s: strategy.score(s, ctx, _MAX)).id

        assert nearest_id(NearestStrategy()) == nearest_id(DijkstraStrategy())
        assert nearest_id(NearestStrategy()) == s_near.id


# ---------------------------------------------------------------------------
# RangeAwareStrategy
# ---------------------------------------------------------------------------

class TestRangeAwareStrategy:
    def test_range_aware_penalises_distant_station_on_low_battery(self):
        origin_lat, origin_lon = 51.5, -0.1
        # 0.45° latitude ≈ 50 km
        s_far = _make_station(lat=origin_lat + 0.45, lon=origin_lon)

        ctx = _ctx(
            origin_lat, origin_lon,
            battery_level_percent=5.0,
            battery_capacity_kwh=60.0,
        )

        score = RangeAwareStrategy().score(s_far, ctx, _MAX)
        assert score > 1e5

    def test_range_aware_no_penalty_when_battery_sufficient(self):
        origin_lat, origin_lon = 51.5, -0.1
        # Use calibrated arrival rate (0.75/hr → ρ=0.5) so base score is small;
        # the assertion verifies no range penalty is added on top.
        s_near = _make_station(lat=origin_lat + 0.009, lon=origin_lon, arrival_rate=0.75)

        ctx = _ctx(
            origin_lat, origin_lon,
            battery_level_percent=80.0,
            battery_capacity_kwh=60.0,
        )

        score = RangeAwareStrategy().score(s_near, ctx, _MAX)
        assert score < 10.0
