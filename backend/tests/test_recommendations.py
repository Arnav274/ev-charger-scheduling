"""POST /recommendations end to end: PostGIS candidate search, reservation lookahead, ranking."""

from datetime import timedelta

import pytest

import app.algorithms as algorithms
import app.recommendation as recommendation
from app.config import settings
from app.dijkstra import RoadGraphUnavailable
from app.models import Reservation
from app.routing_osrm import TravelMetric
from tests.road_graphs import grid_graph

ORIGIN = {"origin_lat": 51.5074, "origin_lon": -0.1278}


@pytest.fixture(autouse=True)
def no_osrm(monkeypatch):
    """Tests use the straight-line fallback unless they install their own road distances."""
    monkeypatch.setattr(recommendation, "route_one_to_many", lambda **_: None)


# A street grid over the test area, 0.0025 degrees (~280 m by ~170 m) per block.
TEST_GRAPH = grid_graph(rows=90, cols=4, spacing_deg=0.0025, lat0=51.50, lon0=-0.1353)


@pytest.fixture(autouse=True)
def road_graph(monkeypatch):
    monkeypatch.setattr(algorithms, "get_road_graph", lambda: TEST_GRAPH)


def post(client, **body):
    return client.post("/recommendations", json={**ORIGIN, **body})


@pytest.mark.parametrize(
    "algorithm", ["nearest", "dijkstra", "cost_optimized", "static_queue", "queue_aware", "range_aware"]
)
def test_every_strategy_returns_ranked_results(client, make_station, algorithm) -> None:
    for i in range(4):
        make_station(lat=51.5074 + 0.005 * (i + 1), chargers=i + 1)

    response = post(client, algorithm=algorithm, top_k=3)

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    assert [r["score"] for r in rows] == sorted(r["score"] for r in rows)
    for row in rows:
        assert row["lat"] > 51.5
        assert row["travel_distance_km"] > 0
        assert 0 <= row["probability_of_delay"] <= 1
        assert row["predicted_wait_min"] >= 0


def test_dijkstra_reports_the_route_it_found(client, make_station) -> None:
    make_station(lat=51.53, name="North")
    row = post(client, algorithm="dijkstra", top_k=1).json()[0]

    # ~2.5 km north along the grid at 10 m/s, plus short access legs at either end.
    assert row["travel_distance_km"] == pytest.approx(2.5, abs=0.2)
    assert row["travel_time_min"] == pytest.approx(row["score"])
    assert row["travel_time_min"] == pytest.approx(2.5 * 1000 / 10 / 60, rel=0.15)


def test_dijkstra_without_a_built_graph_is_503(client, make_station, monkeypatch) -> None:
    make_station()

    def missing():
        raise RoadGraphUnavailable(f"Road graph not found at {settings.road_graph_path}")

    monkeypatch.setattr(algorithms, "get_road_graph", missing)
    response = post(client, algorithm="dijkstra")
    assert response.status_code == 503
    assert "Road graph not found" in response.json()["detail"]


def test_unknown_algorithm_is_rejected(client) -> None:
    assert post(client, algorithm="teleport").status_code == 422


def test_nearest_prefers_the_closest_station(client, make_station) -> None:
    make_station(lat=51.53, name="Far")
    make_station(lat=51.51, name="Near")
    assert post(client, algorithm="nearest", top_k=1).json()[0]["station_name"] == "Near"


def test_nearest_uses_road_distance_when_osrm_answers(client, make_station, monkeypatch) -> None:
    # "Close" is closer as the crow flies but, say, across the river with no bridge nearby.
    make_station(lat=51.510, name="Close")
    make_station(lat=51.515, name="Bridge side")

    def fake_osrm(*, origin_lat, origin_lon, destinations):
        return [TravelMetric(6.0 if lat < 51.512 else 1.5, 10.0) for lat, _ in destinations]

    monkeypatch.setattr(recommendation, "route_one_to_many", fake_osrm)
    assert post(client, algorithm="nearest", top_k=1).json()[0]["station_name"] == "Bridge side"


def test_unroutable_stations_are_dropped(client, make_station, monkeypatch) -> None:
    make_station(lat=51.51, name="Island")
    make_station(lat=51.52, name="Mainland")
    monkeypatch.setattr(
        recommendation,
        "route_one_to_many",
        lambda *, destinations, **_: [
            TravelMetric(float("inf"), float("inf")) if lat < 51.515 else TravelMetric(2.0, 6.0)
            for lat, _ in destinations
        ],
    )
    assert [r["station_name"] for r in post(client, algorithm="nearest").json()] == ["Mainland"]


def test_queue_strategies_avoid_a_single_charger_station(client, make_station) -> None:
    make_station(lat=51.510, chargers=1, name="Single")
    make_station(lat=51.512, chargers=4, name="Hub")

    assert post(client, algorithm="nearest", top_k=1).json()[0]["station_name"] == "Single"
    assert post(client, algorithm="static_queue", top_k=1).json()[0]["station_name"] == "Hub"


def test_queue_aware_counts_bookings_in_the_arrival_window(client, db, make_station, user, now) -> None:
    station = make_station(chargers=2)
    for charger in station.chargers:
        db.add(
            Reservation(
                charger_id=charger.id,
                user_id=user.id,
                start_time=now + timedelta(minutes=5),
                end_time=now + timedelta(minutes=50),
            )
        )
    db.flush()
    body = {"top_k": 1, "arrival_time_target": now.isoformat(), "arrival_window_minutes": 30}

    static = post(client, algorithm="static_queue", **body).json()[0]
    aware = post(client, algorithm="queue_aware", **body).json()[0]

    # Both chargers are booked, so queue_aware models a single free charger.
    assert aware["predicted_wait_min"] > static["predicted_wait_min"]
    assert aware["probability_of_delay"] > static["probability_of_delay"]


def test_bookings_outside_the_window_are_ignored(client, db, make_station, user, now) -> None:
    station = make_station(chargers=2)
    db.add(
        Reservation(
            charger_id=station.chargers[0].id,
            user_id=user.id,
            start_time=now + timedelta(hours=3),
            end_time=now + timedelta(hours=4),
        )
    )
    db.flush()
    body = {"top_k": 1, "arrival_time_target": now.isoformat(), "arrival_window_minutes": 30}

    static = post(client, algorithm="static_queue", **body).json()[0]
    aware = post(client, algorithm="queue_aware", **body).json()[0]
    assert aware["predicted_wait_min"] == pytest.approx(static["predicted_wait_min"])


def test_current_occupancy_is_reported(client, db, make_station, user, now) -> None:
    station = make_station(chargers=3)
    db.add(
        Reservation(
            charger_id=station.chargers[0].id,
            user_id=user.id,
            start_time=now - timedelta(minutes=10),
            end_time=now + timedelta(minutes=20),
        )
    )
    db.flush()
    assert post(client, algorithm="nearest").json()[0]["current_occupancy"] == 1


def test_range_aware_skips_stations_beyond_the_battery(client, make_station) -> None:
    make_station(lat=51.515, chargers=1, name="Reachable but busy")
    make_station(lat=51.700, chargers=6, name="Out of range")  # ~21 km away
    body = {"top_k": 1, "radius_km": 30, "battery_level_percent": 10, "battery_capacity_kwh": 40}

    # 4 kWh left, 2 kWh reserve, 0.2 kWh/km: about 10 km of usable range.
    assert post(client, algorithm="range_aware", **body).json()[0]["station_name"] == "Reachable but busy"


def test_falls_back_to_the_nearest_stations_when_none_are_in_radius(client, make_station) -> None:
    make_station(lat=51.60, name="Outside")
    rows = post(client, algorithm="nearest", radius_km=1).json()
    assert [r["station_name"] for r in rows] == ["Outside"]


def test_empty_database_returns_nothing(client) -> None:
    assert post(client, algorithm="nearest").json() == []


@pytest.mark.parametrize(
    "field,value",
    [("top_k", 0), ("radius_km", 0), ("battery_level_percent", 120), ("weights", [1, -1, 1])],
)
def test_invalid_requests_are_rejected(client, field, value) -> None:
    assert post(client, algorithm="nearest", **{field: value}).status_code == 422
