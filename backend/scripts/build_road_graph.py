"""Build the directed road graph that DijkstraStrategy searches.

Reads the Greater London OpenStreetMap extract that the osm-download service
fetches for OSRM, keeps the roads a car may use, and writes a compact graph:

* nodes are road junctions (and dead ends); the shape points in between are
  folded into the edge, so a residential street with forty nodes becomes one
  edge carrying its full length;
* each edge has a length in metres and a free-flow travel time in seconds;
* one-way streets only get an edge in their direction of travel;
* only the largest strongly connected component is kept, so every node can
  reach every other and a search never gets stuck on an isolated car park.

    docker compose exec backend python -m scripts.build_road_graph
"""

from __future__ import annotations

import argparse
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import osmium
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from app.config import settings
from app.geo import EARTH_RADIUS_KM

# Free-flow speeds (km/h) for roads without a usable maxspeed tag. These follow
# the defaults in OSRM's car profile so the two engines start from the same
# assumptions; docs/road_graph_validation.md compares their results.
DEFAULT_SPEED_KMH = {
    "motorway": 90,
    "motorway_link": 45,
    "trunk": 85,
    "trunk_link": 40,
    "primary": 65,
    "primary_link": 30,
    "secondary": 55,
    "secondary_link": 25,
    "tertiary": 40,
    "tertiary_link": 20,
    "unclassified": 25,
    "residential": 25,
    "living_street": 10,
    "service": 15,
    "road": 25,
}
# Drivers rarely hold the posted limit through junctions and traffic, so a
# tagged maxspeed is scaled down before use.
MAXSPEED_FACTOR = 0.8
MPH_TO_KMH = 1.609344

EXCLUDED_SERVICE = {"parking_aisle", "driveway", "drive-through", "emergency_access"}
NO_ACCESS = {"no", "private", "agricultural", "forestry", "delivery"}


def parse_maxspeed(value: str | None) -> float | None:
    """Speed in km/h from an OSM maxspeed tag such as '30', '20 mph' or '48 km/h'."""
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?\s*", value)
    if not match:
        return None  # 'none', 'signals', 'GB:national' and similar
    speed = float(match.group(1))
    return speed * MPH_TO_KMH if match.group(2) == "mph" else speed


def is_drivable(tags) -> bool:
    highway = tags.get("highway")
    if highway not in DEFAULT_SPEED_KMH:
        return False
    if highway == "service" and tags.get("service") in EXCLUDED_SERVICE:
        return False
    if tags.get("area") == "yes":
        return False
    return tags.get("motor_vehicle", tags.get("access")) not in NO_ACCESS


def direction(tags) -> int:
    """1 for one-way along the way, -1 for one-way against it, 0 for both directions."""
    oneway = tags.get("oneway")
    if oneway in {"yes", "true", "1"}:
        return 1
    if oneway == "-1":
        return -1
    if oneway == "no":
        return 0
    if tags.get("junction") in {"roundabout", "circular"} or tags.get("highway") in {"motorway"}:
        return 1
    return 0


def speed_kmh(tags) -> float:
    posted = parse_maxspeed(tags.get("maxspeed"))
    if posted:
        return posted * MAXSPEED_FACTOR
    return DEFAULT_SPEED_KMH[tags["highway"]]


@dataclass
class Way:
    node_ids: list[int]
    lats: list[float]
    lons: list[float]
    direction: int
    speed_kmh: float


class DrivableWayCollector(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.ways: list[Way] = []

    def way(self, w) -> None:
        if not is_drivable(w.tags):
            return
        nodes = [n for n in w.nodes if n.location.valid()]
        if len(nodes) < 2:
            return
        self.ways.append(
            Way(
                node_ids=[n.ref for n in nodes],
                lats=[n.location.lat for n in nodes],
                lons=[n.location.lon for n in nodes],
                direction=direction(w.tags),
                speed_kmh=speed_kmh(w.tags),
            )
        )


def segment_lengths_m(lats: list[float], lons: list[float]) -> np.ndarray:
    lat, lon = np.radians(lats), np.radians(lons)
    a = np.sin(np.diff(lat) / 2) ** 2 + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(np.diff(lon) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * 1000 * np.arcsin(np.sqrt(a))


@dataclass
class EdgeList:
    src: list[int] = field(default_factory=list)
    dst: list[int] = field(default_factory=list)
    length_m: list[float] = field(default_factory=list)
    time_s: list[float] = field(default_factory=list)

    def add(self, u: int, v: int, length_m: float, time_s: float) -> None:
        self.src.append(u)
        self.dst.append(v)
        self.length_m.append(length_m)
        self.time_s.append(time_s)


def build_graph(ways: list[Way]) -> dict[str, np.ndarray]:
    # A node is a junction if more than one way uses it, or it appears twice in
    # one way (a loop). Way ends are kept too, so dead ends stay reachable.
    uses = Counter(n for way in ways for n in way.node_ids)
    for way in ways:
        uses[way.node_ids[0]] += 2
        uses[way.node_ids[-1]] += 2

    index: dict[int, int] = {}
    lat: list[float] = []
    lon: list[float] = []

    def node_index(osm_id: int, node_lat: float, node_lon: float) -> int:
        if osm_id not in index:
            index[osm_id] = len(lat)
            lat.append(node_lat)
            lon.append(node_lon)
        return index[osm_id]

    edges = EdgeList()
    for way in ways:
        lengths = segment_lengths_m(way.lats, way.lons)
        metres_per_second = way.speed_kmh / 3.6
        start = node_index(way.node_ids[0], way.lats[0], way.lons[0])
        run = 0.0
        for i in range(1, len(way.node_ids)):
            run += float(lengths[i - 1])
            if uses[way.node_ids[i]] < 2:
                continue
            end = node_index(way.node_ids[i], way.lats[i], way.lons[i])
            if end != start:
                seconds = run / metres_per_second
                if way.direction >= 0:
                    edges.add(start, end, run, seconds)
                if way.direction <= 0:
                    edges.add(end, start, run, seconds)
            start, run = end, 0.0

    return keep_largest_component(
        np.array(lat), np.array(lon), np.array(edges.src), np.array(edges.dst), edges
    )


def keep_largest_component(
    lat: np.ndarray, lon: np.ndarray, src: np.ndarray, dst: np.ndarray, edges: EdgeList
) -> dict[str, np.ndarray]:
    n = len(lat)
    adjacency = csr_matrix((np.ones(len(src)), (src, dst)), shape=(n, n))
    _, labels = connected_components(adjacency, directed=True, connection="strong")
    largest = np.bincount(labels).argmax()
    keep = labels == largest

    new_index = np.full(n, -1, dtype=np.int64)
    new_index[keep] = np.arange(int(keep.sum()))
    edge_kept = keep[src] & keep[dst]
    u, v = new_index[src[edge_kept]], new_index[dst[edge_kept]]
    length_m = np.array(edges.length_m)[edge_kept]
    time_s = np.array(edges.time_s)[edge_kept]

    # Compressed sparse row layout: the out-edges of node i are indptr[i]:indptr[i+1].
    order = np.argsort(u, kind="stable")
    indptr = np.concatenate([[0], np.cumsum(np.bincount(u, minlength=int(keep.sum())))])
    return {
        "lat": lat[keep],
        "lon": lon[keep],
        "indptr": indptr.astype(np.int64),
        "indices": v[order].astype(np.int32),
        "length_m": length_m[order].astype(np.float32),
        "time_s": time_s[order].astype(np.float32),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pbf", type=Path, default=settings.osm_pbf_path)
    parser.add_argument("--out", type=Path, default=settings.road_graph_path)
    args = parser.parse_args()

    if not args.pbf.is_file():
        raise SystemExit(f"{args.pbf} not found. Run `docker compose up osm-download` first.")

    started = time.perf_counter()
    collector = DrivableWayCollector()
    collector.apply_file(str(args.pbf), locations=True)
    graph = build_graph(collector.ways)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, **graph)
    print(
        f"{len(collector.ways):,} drivable ways -> {len(graph['lat']):,} junctions, "
        f"{len(graph['indices']):,} directed edges in {time.perf_counter() - started:.0f}s. Wrote {args.out}"
    )


if __name__ == "__main__":
    main()
