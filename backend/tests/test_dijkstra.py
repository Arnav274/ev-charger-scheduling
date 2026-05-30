"""Tests for app.dijkstra."""

import math
import pytest

from app.dijkstra import (
    Station,
    RouteResult,
    haversine_km,
    shortest_paths_to_stations,
)


# Helpers


# Degree offset along a meridian: 1 degree latitude ≈ 111.195 km.
# Using (0.0, 0.0) as origin keeps haversine symmetric and easy to reason about.
_ORIGIN_LAT = 0.0
_ORIGIN_LON = 0.0
_KM_PER_DEG = 111.195


def _station_at_km(station_id: str, km: float) -> Station:
    lat_offset = km / _KM_PER_DEG
    return Station(station_id=station_id, lat=_ORIGIN_LAT + lat_offset, lon=_ORIGIN_LON)


# haversine_km sanity checks

class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_km(51.0, 0.0, 51.0, 0.0) == pytest.approx(0.0)

    def test_symmetric(self):
        d1 = haversine_km(0.0, 0.0, 1.0, 1.0)
        d2 = haversine_km(1.0, 1.0, 0.0, 0.0)
        assert d1 == pytest.approx(d2)

    def test_known_distance(self):
        # Norwich to London is roughly 160 km; just check order of magnitude.
        d = haversine_km(52.63, 1.30, 51.50, 0.12)
        assert 140.0 < d < 180.0



# shortest_paths_to_stations


class TestShortestPaths:




    def test_nearest_station_identified_correctly(self):
        stations = [
            _station_at_km("far", 10.0),
            _station_at_km("near", 1.0),
            _station_at_km("mid", 5.0),
        ]
        results = shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, stations)

        nearest_id = min(results, key=lambda sid: results[sid].distance_km)
        assert nearest_id == "near"






    def test_three_stations_ordering(self):
        stations = [
            _station_at_km("5km", 5.0),
            _station_at_km("1km", 1.0),
            _station_at_km("2km", 2.0),
        ]
        results = shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, stations)

        ordered = sorted(results.values(), key=lambda r: r.distance_km)
        assert [r.station_id for r in ordered] == ["1km", "2km", "5km"]

    def test_three_stations_distances_approx(self):
        stations = [
            _station_at_km("1km", 1.0),
            _station_at_km("2km", 2.0),
            _station_at_km("5km", 5.0),
        ]







        results = shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, stations)

        assert results["1km"].distance_km == pytest.approx(1.0, abs=0.05)
        assert results["2km"].distance_km == pytest.approx(2.0, abs=0.05)
        assert results["5km"].distance_km == pytest.approx(5.0, abs=0.05)






    def test_single_station_distance_positive(self):
        stations = [Station(station_id="only", lat=1.0, lon=1.0)]
        results = shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, stations)

        assert len(results) == 1
        assert results["only"].distance_km > 0.0

    def test_path_starts_at_origin_node(self):
        stations = [
            _station_at_km("A", 3.0),
            _station_at_km("B", 7.0),
            _station_at_km("C", 12.0),
        ]
        results = shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, stations)




        for result in results.values():
            assert result.path_nodes, f"path_nodes is empty for {result.station_id}"
            assert result.path_nodes[0] == 0, (
                f"Path for {result.station_id} starts at node "
                f"{result.path_nodes[0]}, expected 0"
            )




    def test_path_ends_at_correct_station_node(self):
        stations = [
            _station_at_km("X", 2.0),
            _station_at_km("Y", 4.0),
        ]
        results = shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, stations)



        # Stations are indexed 1, 2
        for idx, station in enumerate(stations, start=1):
            path = results[station.station_id].path_nodes
            assert path[-1] == idx, (
                f"Path for {station.station_id} ends at node {path[-1]}, expected {idx}"
            )







    def test_returns_all_stations(self):
        stations = [_station_at_km(f"S{i}", float(i)) for i in range(1, 6)]
        results = shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, stations)

        assert set(results.keys()) == {s.station_id for s in stations}

    def test_empty_stations_raises(self):
        with pytest.raises(ValueError):
            shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, [])







    def test_route_result_fields(self):
        stations = [_station_at_km("Z", 2.0)]
        results = shortest_paths_to_stations(_ORIGIN_LAT, _ORIGIN_LON, stations)
        r = results["Z"]

        assert isinstance(r, RouteResult)
        assert isinstance(r.station_id, str)
        assert isinstance(r.distance_km, float)
        assert isinstance(r.path_nodes, list)
