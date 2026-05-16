"""
Dijkstra shortest-path routing for EV charging station selection.

This module builds a complete weighted graph over a set of geographic nodes
(an origin point plus a collection of charging stations), where each edge
weight is the haversine great-circle distance in kilometres between the two
endpoints. Dijkstra's algorithm is then run from the origin to produce the
shortest-path distance to every station.

Graph representation
--------------------
Nodes are indexed 0 … N where:
  - node 0  : the EV's current location (origin)
  - node 1…N: the charging stations in the order they are supplied

Edges are undirected; a complete graph is built so every pair of nodes is
connected. This ensures Dijkstra always finds a path even when no real road
network is modelled — the haversine distance acts as a lower-bound proxy for
road distance.

Why complete-graph Dijkstra rather than plain haversine
-------------------------------------------------------
When all N candidate stations are passed together as a single graph, each
station acts as a potential *intermediate waypoint* on the path to every other
station. Dijkstra therefore exploits "detour" routes that pass through an
intermediate node when that triangular path is shorter than the direct edge —
precisely the classic shortest-path relaxation. While haversine on a sphere
satisfies the triangle inequality and such shortcuts are therefore absent for
pure great-circle distances, the complete-graph formulation is the natural
framework for richer topologies: known road junctions, motorway interchanges,
or any set of geographic waypoints can be inserted into the node list and the
algorithm will automatically route through them if doing so shortens the path.
This makes the complete-graph Dijkstra implementation a principled, extensible
baseline — the academic justification for preferring it over a plain haversine
point-to-point calculation in the dissertation comparison.

Algorithm overview
------------------
Dijkstra's algorithm maintains a min-heap priority queue of (tentative_dist,
node_index) tuples. It relaxes neighbouring edges greedily: at each step the
node with the current smallest tentative distance is settled, and its
unvisited neighbours are updated if a shorter route through that node exists.
The process terminates once all nodes have been settled.

Complexity: O((V + E) log V) with a binary heap. For a complete graph
E = V*(V-1)/2, so effectively O(V² log V).
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Station:
    """A charging station node in the routing graph.

    Attributes:
        station_id: Unique identifier (e.g. database primary key or OCM ID).
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
    """
    station_id: str
    lat: float
    lon: float


@dataclass
class RouteResult:
    """The shortest-path result from the origin to a single station.

    Attributes:
        station_id: The target station identifier.
        distance_km: Total great-circle path length in kilometres.
        path_nodes: Ordered list of node indices from origin (0) to the
            station node, representing the shortest path through the graph.
    """
    station_id: str
    distance_km: float
    path_nodes: List[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

_EARTH_RADIUS_KM = 6_371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute the great-circle distance between two geographic points.

    Uses the haversine formula, which is numerically well-conditioned for
    short distances and accurate to within ~0.5 % for distances up to a few
    thousand kilometres.

    Args:
        lat1: Latitude of point 1 in decimal degrees.
        lon1: Longitude of point 1 in decimal degrees.
        lat2: Latitude of point 2 in decimal degrees.
        lon2: Longitude of point 2 in decimal degrees.

    Returns:
        Distance in kilometres as a float.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2.0 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_graph(
    origin_lat: float,
    origin_lon: float,
    stations: List[Station],
) -> Tuple[List[Tuple[float, float]], List[List[Tuple[int, float]]]]:
    """Build a complete weighted undirected adjacency list.

    Node 0 is the origin; nodes 1…N correspond to stations[0]…stations[N-1].

    Args:
        origin_lat: Origin latitude in decimal degrees.
        origin_lon: Origin longitude in decimal degrees.
        stations: Ordered list of Station objects.

    Returns:
        A tuple of:
            coords   – list of (lat, lon) for every node in index order.
            adj      – adjacency list; adj[i] is a list of (j, weight_km)
                       for every other node j reachable from i.
    """
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


# ---------------------------------------------------------------------------
# Dijkstra's algorithm
# ---------------------------------------------------------------------------

def _dijkstra(
    adj: List[List[Tuple[int, float]]],
    source: int,
) -> Tuple[List[float], List[Optional[int]]]:
    """Run Dijkstra's single-source shortest-path algorithm.

    Starting from *source*, relax edges via a min-heap until all reachable
    nodes are settled. Distances to unreachable nodes remain infinity.

    Args:
        adj: Adjacency list where adj[u] = [(v, weight), …].
        source: Index of the source node (0 for the EV origin).

    Returns:
        A tuple of:
            dist  – dist[v] is the shortest-path distance from source to v.
            prev  – prev[v] is the predecessor of v on the shortest path;
                    None if v is the source or unreachable.

    Algorithm steps:
        1. Initialise dist[source] = 0, all others = ∞.
        2. Push (0, source) onto the priority queue.
        3. Pop the minimum-distance unsettled node u.
        4. For each neighbour v of u, if dist[u] + w(u,v) < dist[v], update
           dist[v] and prev[v], then push (new_dist, v) onto the heap.
        5. Repeat from step 3 until the heap is empty.
        6. Lazy deletion: skip a popped node if its recorded distance is
           already smaller (stale heap entry from a previous relaxation).
    """
    n = len(adj)
    dist: List[float] = [math.inf] * n
    prev: List[Optional[int]] = [None] * n
    dist[source] = 0.0

    # heap entries: (tentative_distance, node_index)
    heap: List[Tuple[float, int]] = [(0.0, source)]

    while heap:
        d_u, u = heapq.heappop(heap)

        # Lazy deletion — stale entry, skip
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
    """Walk the predecessor array back from *target* to the source.

    Args:
        prev: Predecessor array produced by :func:`_dijkstra`.
        target: Destination node index.

    Returns:
        List of node indices from source to target (inclusive), or an empty
        list if no path exists.
    """
    path: List[int] = []
    node: Optional[int] = target
    while node is not None:
        path.append(node)
        node = prev[node]
    path.reverse()
    # If the path does not start at a node with prev=None chain it means the
    # target is unreachable (dist was still inf).
    if not path or prev[path[0]] is not None and len(path) == 1:
        return []
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def shortest_paths_to_stations(
    origin_lat: float,
    origin_lon: float,
    stations: List[Station],
) -> Dict[str, RouteResult]:
    """Find the shortest haversine path from an origin to every charging station.

    Constructs a complete weighted graph (origin + all stations as nodes,
    haversine distances as edge weights) and runs Dijkstra's algorithm from
    the origin node.

    Args:
        origin_lat: Current latitude of the EV in decimal degrees.
        origin_lon: Current longitude of the EV in decimal degrees.
        stations: List of :class:`Station` objects to route to. Must be
            non-empty.

    Returns:
        A dict mapping each ``station_id`` to a :class:`RouteResult` holding
        the shortest distance in kilometres and the node-index path taken.

    Raises:
        ValueError: If *stations* is empty.

    Example::

        from backend.app.dijkstra import Station, shortest_paths_to_stations

        ev_lat, ev_lon = 52.6309, 1.2974  # Norwich city centre
        stations = [
            Station("S1", 52.6270, 1.2960),
            Station("S2", 52.6350, 1.3100),
        ]
        results = shortest_paths_to_stations(ev_lat, ev_lon, stations)
        for r in results.values():
            print(r.station_id, round(r.distance_km, 3), r.path_nodes)
    """
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


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Toy example with 4 nodes: 1 origin + 3 stations.

    Node layout (approximate Norwich area):
        Origin  : 52.6309 N, 1.2974 E  (city centre)
        S1      : 52.6270 N, 1.2960 E  (~ 0.4 km south)
        S2      : 52.6350 N, 1.3100 E  (~ 1.4 km north-east)
        S3      : 52.6400 N, 1.2800 E  (~ 1.2 km north-west)
    """
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
