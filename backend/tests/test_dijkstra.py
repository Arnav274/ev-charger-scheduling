"""Tests for the Dijkstra search and the RoadGraph wrapper around it."""

import math

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as scipy_dijkstra

from app.dijkstra import ACCESS_SPEED_KMH, RoadGraph, dijkstra
from tests.road_graphs import grid_graph


def csr(n: int, edges: list[tuple[int, int, float]]):
    """(indptr, indices, weights) for a directed graph given as (u, v, weight) edges."""
    edges = sorted(edges)
    indptr = [0] * (n + 1)
    for u, _, _ in edges:
        indptr[u + 1] += 1
    for i in range(n):
        indptr[i + 1] += indptr[i]
    return indptr, [v for _, v, _ in edges], [w for _, _, w in edges]


def two_way(edges):
    return edges + [(v, u, w) for u, v, w in edges]


class TestDijkstra:
    def test_takes_a_cheaper_detour_over_an_expensive_direct_edge(self) -> None:
        indptr, indices, weights = csr(3, [(0, 1, 10.0), (0, 2, 1.0), (2, 1, 1.0)])
        paths = dijkstra(indptr, indices, weights, source=0)
        assert paths.dist == [0.0, 2.0, 1.0]

    def test_respects_one_way_edges(self) -> None:
        indptr, indices, weights = csr(2, [(0, 1, 5.0)])
        assert dijkstra(indptr, indices, weights, source=0).dist[1] == 5.0
        assert math.isinf(dijkstra(indptr, indices, weights, source=1).dist[0])

    def test_unreachable_nodes_stay_infinite(self) -> None:
        indptr, indices, weights = csr(4, two_way([(0, 1, 1.0), (2, 3, 1.0)]))
        paths = dijkstra(indptr, indices, weights, source=0)
        assert paths.reached(1)
        assert not paths.reached(2)
        assert not paths.reached(3)

    def test_stops_once_every_target_is_settled(self) -> None:
        n = 1000
        indptr, indices, weights = csr(n, two_way([(i, i + 1, 1.0) for i in range(n - 1)]))
        paths = dijkstra(indptr, indices, weights, source=0, targets=[3])
        assert paths.dist[3] == 3.0
        assert paths.settled == 4  # nodes 0 to 3, nothing further along the line
        assert math.isinf(paths.dist[10])

    def test_unreachable_target_explores_everything_and_terminates(self) -> None:
        indptr, indices, weights = csr(3, [(0, 1, 1.0)])
        paths = dijkstra(indptr, indices, weights, source=0, targets=[2])
        assert not paths.reached(2)
        assert paths.settled == 2

    def test_zero_weight_edges(self) -> None:
        indptr, indices, weights = csr(3, [(0, 1, 0.0), (1, 2, 0.0)])
        assert dijkstra(indptr, indices, weights, source=0).dist == [0.0, 0.0, 0.0]

    def test_parallel_edges_use_the_cheapest(self) -> None:
        indptr, indices, weights = csr(2, [(0, 1, 7.0), (0, 1, 3.0)])
        assert dijkstra(indptr, indices, weights, source=0).dist[1] == 3.0

    @pytest.mark.parametrize("seed", range(5))
    def test_matches_scipy_on_random_directed_graphs(self, seed: int) -> None:
        rng = np.random.default_rng(seed)
        n = 80
        edges = {
            (int(u), int(v)): float(w)
            for u, v, w in zip(
                rng.integers(0, n, 600), rng.integers(0, n, 600), rng.uniform(0, 10, 600), strict=True
            )
            if u != v
        }
        indptr, indices, weights = csr(n, [(u, v, w) for (u, v), w in edges.items()])
        matrix = csr_matrix((weights, indices, indptr), shape=(n, n))

        for source in rng.integers(0, n, 5):
            ours = dijkstra(indptr, indices, weights, source=int(source)).dist
            expected = scipy_dijkstra(matrix, directed=True, indices=int(source))
            assert ours == pytest.approx(expected.tolist())


class TestRoadGraph:
    def test_snaps_points_to_the_nearest_junction(self) -> None:
        graph = grid_graph()
        nodes, distances = graph.nearest_nodes([(51.5, -0.1), (51.5021, -0.0989)])
        assert nodes == [0, 2 * 4 + 1]
        assert distances[0] == pytest.approx(0, abs=0.1)
        assert distances[1] == pytest.approx(math.hypot(11.1, 6.9), rel=0.05)

    def test_route_between_junctions_follows_the_grid(self) -> None:
        graph = grid_graph()
        (route,) = graph.fastest_routes((51.5, -0.1), [(51.503, -0.097)])
        # Three blocks north and three east.
        assert route.distance_km == pytest.approx((3 * 111.195 + 3 * 69.22) / 1000, rel=0.01)
        assert route.duration_min == pytest.approx(route.distance_km * 1000 / 10 / 60, rel=0.01)

    def test_access_legs_are_added_at_the_access_speed(self) -> None:
        graph = grid_graph()
        (exact,) = graph.fastest_routes((51.5, -0.1), [(51.501, -0.1)])
        (offset,) = graph.fastest_routes((51.5, -0.1), [(51.501, -0.1003)])  # ~21 m west of node 4
        extra_m = (offset.distance_km - exact.distance_km) * 1000
        assert extra_m == pytest.approx(20.8, abs=1)
        assert (offset.duration_min - exact.duration_min) * 60 == pytest.approx(
            extra_m / (ACCESS_SPEED_KMH / 3.6), rel=0.01
        )

    def test_path_reconstruction_walks_back_to_the_source(self) -> None:
        graph = grid_graph()
        paths = dijkstra(graph.indptr, graph.indices, graph.time_s, source=0)
        path = graph.path(paths, 15)
        assert path[0] == 0
        assert path[-1] == 15
        assert len(path) == 7  # six blocks, seven junctions
        assert graph.path_length_m(paths, 15) == pytest.approx(3 * 111.195 + 3 * 69.22, rel=1e-3)

    def test_unreachable_destination_is_none(self) -> None:
        lat, lon = np.array([51.5, 51.51]), np.array([-0.1, -0.1])
        one_way = RoadGraph(
            lat, lon, np.array([0, 1, 1]), np.array([1]), np.array([1000.0]), np.array([60.0])
        )
        assert one_way.fastest_routes((51.51, -0.1), [(51.5, -0.1)]) == [None]
        assert one_way.fastest_routes((51.5, -0.1), [(51.51, -0.1)])[0] is not None

    def test_no_destinations(self) -> None:
        assert grid_graph().fastest_routes((51.5, -0.1), []) == []

    def test_save_and_load_round_trip(self, tmp_path) -> None:
        graph = grid_graph()
        path = tmp_path / "graph.npz"
        np.savez(
            path,
            lat=graph.lat,
            lon=graph.lon,
            indptr=np.array(graph.indptr),
            indices=np.array(graph.indices),
            length_m=np.array(graph.length_m),
            time_s=np.array(graph.time_s),
        )
        loaded = RoadGraph.load(path)
        assert loaded.fastest_routes((51.5, -0.1), [(51.503, -0.097)]) == graph.fastest_routes(
            (51.5, -0.1), [(51.503, -0.097)]
        )
