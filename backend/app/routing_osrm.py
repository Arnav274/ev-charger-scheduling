"""Road distance and drive time from the self-hosted OSRM server."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

import requests

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TravelMetric:
    distance_km: float
    duration_min: float


def _coords(lat: float, lon: float) -> str:
    return f"{lon:.6f},{lat:.6f}"  # OSRM takes lon,lat


@lru_cache(maxsize=2048)
def _table(origin: str, destinations: str) -> dict:
    """One OSRM table request from a single origin (index 0) to many destinations."""
    res = requests.get(
        f"{settings.osrm_base_url.rstrip('/')}/table/v1/driving/{origin};{destinations}",
        params={"annotations": "distance,duration", "sources": "0"},
        timeout=20,
    )
    res.raise_for_status()
    return res.json()


def route_one_to_many(
    *, origin_lat: float, origin_lon: float, destinations: Iterable[tuple[float, float]]
) -> list[TravelMetric] | None:
    """Road distance and duration to each destination, in order.

    Returns None when OSRM is unavailable so the caller can fall back to
    straight-line estimates. Pairs OSRM cannot route come back as infinity.
    """
    dest_list = list(destinations)
    if not dest_list:
        return []

    try:
        payload = _table(
            _coords(origin_lat, origin_lon), ";".join(_coords(lat, lon) for lat, lon in dest_list)
        )
        distances = payload["distances"][0][1:]
        durations = payload["durations"][0][1:]
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        logger.warning("OSRM table request failed, falling back to straight-line travel: %s", exc)
        return None

    return [
        TravelMetric(float("inf"), float("inf"))
        if d_m is None or t_s is None
        else TravelMetric(d_m / 1000.0, t_s / 60.0)
        for d_m, t_s in zip(distances, durations, strict=True)
    ]
