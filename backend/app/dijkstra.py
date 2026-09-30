"""Dijkstra's shortest-path algorithm over the London road graph.

The graph is built from OpenStreetMap by scripts/build_road_graph.py and
stored in compressed sparse row (CSR) form: the out-edges of node u are
indices[indptr[u]:indptr[u + 1]], with matching entries in each weight array.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from app.config import settings
from app.geo import EARTH_RADIUS_KM

# Driving between a point and the junction it snaps to is costed at this speed.
# Junctions in central London are rarely more than ~100 m apart, so the leg is short.
ACCESS_SPEED_KMH = 15.0


class RoadGraphUnavailable(RuntimeError):
    """Raised when the road graph file has not been built yet."""


@dataclass
class ShortestPaths:
    dist: list[float]
    # Index of the edge used to reach each node, or -1 for the source and unreached nodes.
    prev_edge: list[int]
    settled: int

    def reached(self, node: int) -> bool:
        return not math.isinf(self.dist[node])


def dijkstra(
    indptr: Sequence[int],
    indices: Sequence[int],
    weights: Sequence[float],
    source: int,
    targets: Iterable[int] | None = None,
) -> ShortestPaths:
    """Single-source shortest paths using a binary heap with lazy deletion.

    Instead of decreasing a key in place, a node is pushed again whenever a
    shorter distance is found, and stale entries are skipped when popped.
    With `targets`, the search stops as soon as every target is settled, which
    keeps a query for nearby stations from exploring the whole city.
    Runs in O((V + E) log V). Weights must be non-negative.
    """
    n = len(indptr) - 1
    dist = [math.inf] * n
    prev_edge = [-1] * n
    done = [False] * n
    remaining = set(targets) if targets is not None else None
    dist[source] = 0.0
    heap = [(0.0, source)]
    settled = 0

    while heap:
        d, u = heapq.heappop(heap)
        if done[u]:
            continue
        done[u] = True
        settled += 1
        if remaining is not None:
            remaining.discard(u)
            if not remaining:
                break
        for edge in range(indptr[u], indptr[u + 1]):
            v = indices[edge]
            candidate = d + weights[edge]
            if candidate < dist[v]:
                dist[v] = candidate
                prev_edge[v] = edge
                heapq.heappush(heap, (candidate, v))

    return ShortestPaths(dist=dist, prev_edge=prev_edge, settled=settled)


@dataclass(frozen=True)
class RoadTravel:
    distance_km: float
    duration_min: float


class RoadGraph:
    def __init__(
        self,
        lat: np.ndarray,
        lon: np.ndarray,
        indptr: np.ndarray,
        indices: np.ndarray,
        length_m: np.ndarray,
        time_s: np.ndarray,
    ) -> None:
        self.lat, self.lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
        # The search loop runs in pure Python, where list indexing is several
        # times faster than indexing numpy arrays element by element.
        self.indptr = np.asarray(indptr).tolist()
        self.indices = np.asarray(indices).tolist()
        self.length_m = np.asarray(length_m, dtype=float).tolist()
        self.time_s = np.asarray(time_s, dtype=float).tolist()
        self.edge_source = np.repeat(np.arange(len(self.lat)), np.diff(indptr)).tolist()
        # A flat projection is accurate to well under 1% across a city.
        self._lat0 = math.radians(float(np.mean(self.lat))) if len(self.lat) else 0.0
        self._tree = cKDTree(self._project(self.lat, self.lon))

    @classmethod
    def load(cls, path: Path) -> RoadGraph:
        with np.load(path) as data:
            return cls(**{key: data[key] for key in data.files})

    @property
    def node_count(self) -> int:
        return len(self.lat)

    def _project(self, lat, lon) -> np.ndarray:
        metres_per_radian = EARTH_RADIUS_KM * 1000
        x = np.radians(lon) * math.cos(self._lat0) * metres_per_radian
        y = np.radians(lat) * metres_per_radian
        return np.column_stack([x, y])

    def nearest_nodes(self, points: Sequence[tuple[float, float]]) -> tuple[list[int], list[float]]:
        """Closest junction to each (lat, lon) and the straight-line distance to it in metres."""
        lats, lons = zip(*points, strict=True)
        distance_m, nodes = self._tree.query(self._project(np.array(lats), np.array(lons)))
        return np.atleast_1d(nodes).tolist(), np.atleast_1d(distance_m).tolist()

    def path(self, paths: ShortestPaths, target: int) -> list[int]:
        """Nodes on the shortest path from the search's source to `target`."""
        if not paths.reached(target):
            return []
        nodes = [target]
        edge = paths.prev_edge[target]
        while edge != -1:
            nodes.append(self.edge_source[edge])
            edge = paths.prev_edge[self.edge_source[edge]]
        return nodes[::-1]

    def path_length_m(self, paths: ShortestPaths, target: int) -> float:
        total = 0.0
        edge = paths.prev_edge[target]
        while edge != -1:
            total += self.length_m[edge]
            edge = paths.prev_edge[self.edge_source[edge]]
        return total

    def fastest_routes(
        self, origin: tuple[float, float], destinations: Sequence[tuple[float, float]]
    ) -> list[RoadTravel | None]:
        """Drive time and distance of the fastest route to each destination, None if unreachable."""
        if not destinations:
            return []
        (source,), (origin_snap_m,) = self.nearest_nodes([origin])
        targets, snaps_m = self.nearest_nodes(destinations)
        paths = dijkstra(self.indptr, self.indices, self.time_s, source, targets)

        results: list[RoadTravel | None] = []
        for target, snap_m in zip(targets, snaps_m, strict=True):
            if not paths.reached(target):
                results.append(None)
                continue
            access_m = origin_snap_m + snap_m
            seconds = paths.dist[target] + access_m / (ACCESS_SPEED_KMH / 3.6)
            metres = self.path_length_m(paths, target) + access_m
            results.append(RoadTravel(distance_km=metres / 1000, duration_min=seconds / 60))
        return results


@lru_cache(maxsize=1)
def _load(path: Path) -> RoadGraph:
    return RoadGraph.load(path)


def get_road_graph() -> RoadGraph:
    path = settings.road_graph_path
    if not path.is_file():
        raise RoadGraphUnavailable(
            f"Road graph not found at {path}. Build it with: "
            "docker compose exec backend python -m scripts.build_road_graph"
        )
    return _load(path)
