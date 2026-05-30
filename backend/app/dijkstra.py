"""Dijkstra shortest-path routing over a Haversine graph of charging stations."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# Data structure


@dataclass
class Station:
    station_id: str
    lat: float
    lon: float




@dataclass
class RouteResult:
    station_id: str
    distance_km: float
    path_nodes: List[int] = field(default_factory=list)




# Haversine distance

_EARTH_RADIUS_KM = 6_371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2.0 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))




# Graph construction

def _build_graph(
    origin_lat: float,
    origin_lon: float,
    stations: List[Station],
) -> Tuple[List[Tuple[float, float]], List[List[Tuple[int, float]]]]:
    """Build a complete weighted undirected adjacency list. Node 0 is the origin."""
    coords: List[Tuple[float, float]] = [(origin_lat, origin_lon)]
    for s in stations:
        coords.append((s.lat, s.lon))

    n = len(coords)
    adj: List[List[Tuple[int, float]]] = [[] for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            dist = haversine_km(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
            adj[i].append((j, dist))
            adj[j].append((i, dist))

    return coords, adj




# Dijkstra's algorithm

def _dijkstra(
    adj: List[List[Tuple[int, float]]],
    source: int,
) -> Tuple[List[float], List[Optional[int]]]:
    """Single-source shortest paths from source using a min-heap."""
    n = len(adj)
    dist: List[float] = [math.inf] * n
    prev: List[Optional[int]] = [None] * n
    dist[source] = 0.0

    # heap entries
    heap: List[Tuple[float, int]] = [(0.0, source)]

    while heap:
        d_u, u = heapq.heappop(heap)





        if d_u > dist[u]:
            continue

        for v, weight in adj[u]:
            candidate = dist[u] + weight
            if candidate < dist[v]:
                dist[v] = candidate
                prev[v] = u
                heapq.heappush(heap, (candidate, v))

    return dist, prev






def _reconstruct_path(prev: List[Optional[int]], target: int) -> List[int]:
    path: List[int] = []
    node: Optional[int] = target
    while node is not None:
        path.append(node)
        node = prev[node]
    path.reverse()
    # If the path does not start at a node 
    if not path or prev[path[0]] is not None and len(path) == 1:
        return []
    return path




# Public API




def shortest_paths_to_stations(
    origin_lat: float,
    origin_lon: float,
    stations: List[Station],
) -> Dict[str, RouteResult]:
    """Run Dijkstra from the origin to every station in the list."""
    if not stations:





        raise ValueError("At least one station must be provided.")







    _, adj = _build_graph(origin_lat, origin_lon, stations)
    dist, prev = _dijkstra(adj, source=0)

    results: Dict[str, RouteResult] = {}
    for idx, station in enumerate(stations):
        node_idx = idx + 1  # node 0 is origin
        path = _reconstruct_path(prev, node_idx)
        results[station.station_id] = RouteResult(
            station_id=station.station_id,
            distance_km=dist[node_idx],
            path_nodes=path,
        )






    return results


# demo

if __name__ == "__main__":
    demo_stations = [
        Station(station_id="S1", lat=52.6270, lon=1.2960),
        Station(station_id="S2", lat=52.6350, lon=1.3100),
        Station(station_id="S3", lat=52.6400, lon=1.2800),
    ]


    origin = (52.6309, 1.2974)

    print("Dijkstra shortest-path demo")
    print(f"Origin: lat={origin[0]}, lon={origin[1]}\n")

    results = shortest_paths_to_stations(origin[0], origin[1], demo_stations)

    for station_id, result in sorted(results.items(), key=lambda kv: kv[1].distance_km):
        path_str = " -> ".join(
            "origin" if n == 0 else f"S{n}" for n in result.path_nodes
        )
        print(
            f"  {station_id:>4}  {result.distance_km:6.3f} km   path: {path_str}"
        )

    best_id = min(results, key=lambda sid: results[sid].distance_km)
    print(f"\nNearest station: {best_id} ({results[best_id].distance_km:.3f} km)")

