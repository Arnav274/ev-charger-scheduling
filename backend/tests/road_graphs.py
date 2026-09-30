"""Small synthetic road graphs for tests."""

import math

import numpy as np

from app.dijkstra import RoadGraph


def grid_graph(
    rows: int = 4,
    cols: int = 4,
    spacing_deg: float = 0.001,
    lat0: float = 51.5,
    lon0: float = -0.1,
    speed_ms: float = 10.0,
) -> RoadGraph:
    """A two-way grid of streets starting at (lat0, lon0), driven at a constant speed.

    Node r * cols + c sits at (lat0 + r * spacing, lon0 + c * spacing). With the
    default 0.001 degree spacing a block is about 111 m north-south and 69 m
    east-west, and the default speed is 36 km/h.
    """
    lat = np.repeat(lat0 + np.arange(rows) * spacing_deg, cols)
    lon = np.tile(lon0 + np.arange(cols) * spacing_deg, rows)
    metres_per_deg = 111_195.0
    edges = []
    for r in range(rows):
        for c in range(cols):
            node = r * cols + c
            if c + 1 < cols:
                length = spacing_deg * metres_per_deg * math.cos(math.radians(lat[node]))
                edges += [(node, node + 1, length), (node + 1, node, length)]
            if r + 1 < rows:
                length = spacing_deg * metres_per_deg
                edges += [(node, node + cols, length), (node + cols, node, length)]
    edges.sort()
    src = np.array([u for u, _, _ in edges])
    indptr = np.concatenate([[0], np.cumsum(np.bincount(src, minlength=rows * cols))])
    length_m = np.array([w for _, _, w in edges])
    return RoadGraph(lat, lon, indptr, np.array([v for _, v, _ in edges]), length_m, length_m / speed_ms)
