"""Tests for DijkstraStrategy in app.algorithms."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.algorithms import DijkstraStrategy, RecommendationContext, STRATEGIES


------------------------------------------------------------------
#Helpers



def _make_station(lat: float, lon: float) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.lat = lat
    s.lon = lon
    s.price_pence_per_kwh = 55.0
    s.arrival_rate_per_hour = 4.0
    s.mean_service_minutes = 40.0
    s.chargers = [MagicMock()]
    return s





def _make_context(origin_lat: float = 0.0, origin_lon: float = 0.0) -> RecommendationContext:
    return RecommendationContext(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        weights=(1 / 3, 1 / 3, 1 / 3),
    )


_MAX_VALS = {"distance": 100.0, "wait": 60.0, "cost": 100.0}

_STRATEGY = DijkstraStrategy()

# Registration

def test_dijkstra_registered_in_strategies():
    assert "dijkstra" in STRATEGIES
    assert isinstance(STRATEGIES["dijkstra"], DijkstraStrategy)


# Score correctness

def test_score_is_positive_for_non_coincident_station():
    station = _make_station(lat=1.0, lon=1.0)
    ctx = _make_context(0.0, 0.0)
    score = _STRATEGY.score(station, ctx, _MAX_VALS)
    assert score > 0.0


def test_score_is_haversine_distance():
    from app.dijkstra import haversine_km

    station = _make_station(lat=1.0, lon=0.0)
    ctx = _make_context(0.0, 0.0)
    expected = haversine_km(0.0, 0.0, 1.0, 0.0)
    assert _STRATEGY.score(station, ctx, _MAX_VALS) == pytest.approx(expected, rel=1e-6)


def test_score_increases_with_distance():
    near = _make_station(lat=0.01, lon=0.0)   # ~1.1 km
    far = _make_station(lat=0.10, lon=0.0)    # ~11.1 km
    ctx = _make_context(0.0, 0.0)

    assert _STRATEGY.score(near, ctx, _MAX_VALS) < _STRATEGY.score(far, ctx, _MAX_VALS)


def test_score_is_symmetric():
    station = _make_station(lat=1.0, lon=1.0)
    ctx_ab = _make_context(0.0, 0.0)
    ctx_ba = _make_context(1.0, 1.0)

    station_origin = _make_station(lat=0.0, lon=0.0)

    assert _STRATEGY.score(station, ctx_ab, _MAX_VALS) == pytest.approx(
        _STRATEGY.score(station_origin, ctx_ba, _MAX_VALS), rel=1e-6
    )


def test_score_ignores_travel_by_station():
    station = _make_station(lat=1.0, lon=0.0)
    ctx_no_osrm = _make_context(0.0, 0.0)

    ctx_with_osrm = _make_context(0.0, 0.0)
    # Inject a wrong OSRM distance to confirm Dijkstra score is unaffected.
    ctx_with_osrm.travel_by_station = {str(station.id): (9999.0, 9999.0)}

    assert _STRATEGY.score(station, ctx_no_osrm, _MAX_VALS) == pytest.approx(
        _STRATEGY.score(station, ctx_with_osrm, _MAX_VALS), rel=1e-6
    )


def test_three_stations_ranked_by_dijkstra_distance():
    # Stations at ~1.1 km, ~5.5 km, ~11.1 km north of origin.
    s1 = _make_station(lat=0.01, lon=0.0)
    s2 = _make_station(lat=0.05, lon=0.0)
    s3 = _make_station(lat=0.10, lon=0.0)
    ctx = _make_context(0.0, 0.0)

    scores = {s.id: _STRATEGY.score(s, ctx, _MAX_VALS) for s in [s1, s2, s3]}
    ordered = sorted(scores, key=scores.get)

    assert ordered == [s1.id, s2.id, s3.id]
