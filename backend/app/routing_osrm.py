from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import requests

from app.config import settings


@dataclass(frozen=True)
class TravelMetric:
    distance_km: float
    duration_min: float




def _coords_str(lat: float, lon: float) -> str:
    # OSRM expects lon,lat
    return f"{lon:.6f},{lat:.6f}"




@lru_cache(maxsize=2048)
def _table_cached(origin_lat: float, origin_lon: float, dest_key: str) -> dict:
    """
    Cached OSRM table call for one origin and a specific destination set.
    """
    base = settings.osrm_base_url.rstrip("/")
    coords = f"{_coords_str(origin_lat, origin_lon)};{dest_key}"
    url = f"{base}/table/v1/driving/{coords}"
    res = requests.get(
        url,
        params={
            "annotations": "distance,duration",
            "sources": "0",
        },
        timeout=20,
    )

    res.raise_for_status()
    return res.json()


def route_one_to_many(
    *,
    origin_lat: float,
    origin_lon: float,
    destinations: Iterable[tuple[float, float]],
) -> list[TravelMetric] | None:
    """

    Returns OSRM distance/time from origin to each destination (same order).
    If OSRM is unreachable or errors, returns None (caller should fallback).
    """
    dest_list = list(destinations)
    if not dest_list:
        return []



    try:
        dest_key = ";".join(_coords_str(lat, lon) for lat, lon in dest_list)
        payload = _table_cached(origin_lat, origin_lon, dest_key)
        distances = payload.get("distances", [[]])[0]
        durations = payload.get("durations", [[]])[0]
        out: list[TravelMetric] = []
        for d_m, t_s in zip(distances[1:], durations[1:], strict=False):
            if d_m is None or t_s is None:
                out.append(TravelMetric(distance_km=float("inf"), duration_min=float("inf")))
            else:
                out.append(TravelMetric(distance_km=float(d_m) / 1000.0, duration_min=float(t_s) / 60.0))
        return out
    except Exception:
        return None


