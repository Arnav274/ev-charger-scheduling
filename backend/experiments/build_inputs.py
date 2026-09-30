"""Freeze everything the experiment needs from the live stack into experiments/data/.

Run once, with the database loaded and OSRM and the road graph available:

    docker compose exec backend python -m experiments.build_inputs

It writes the station snapshot, a seeded pool of trip origins for each
scenario, and the travel from every origin to each of its candidate stations,
both from OSRM and from our Dijkstra search. After that the experiment runs
offline, and anyone re-running it gets identical inputs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.dijkstra import get_road_graph
from app.geo import haversine_km
from app.models import Station
from app.recommendation import FALLBACK_NEAREST_COUNT
from app.routing_osrm import route_one_to_many
from app.schemas import RecommendationRequest
from experiments.config import DATA_DIR, ORIGINS_PER_SCENARIO, SCENARIOS, SEED

CANDIDATE_RADIUS_KM = RecommendationRequest.model_fields["radius_km"].default


def draw_origin(scenario: dict, rng: np.random.Generator) -> tuple[float, float]:
    if "centre" in scenario:
        # Uniform over a disc: the square root keeps density even out to the rim.
        lat0, lon0 = scenario["centre"]
        r_km = scenario["radius_km"] * np.sqrt(rng.uniform())
        theta = rng.uniform(0, 2 * np.pi)
        km_per_deg_lat = 111.195
        km_per_deg_lon = km_per_deg_lat * np.cos(np.radians(lat0))
        return lat0 + r_km * np.sin(theta) / km_per_deg_lat, lon0 + r_km * np.cos(theta) / km_per_deg_lon
    return rng.uniform(*scenario["lat_range"]), rng.uniform(*scenario["lon_range"])


def candidates_for(origin: tuple[float, float], stations: list[dict]) -> list[int]:
    """Same rule as the app: stations within the default radius, else the nearest few."""
    distances = [haversine_km(*origin, s["lat"], s["lon"]) for s in stations]
    within = [i for i, d in enumerate(distances) if d <= CANDIDATE_RADIUS_KM]
    return within or sorted(range(len(stations)), key=distances.__getitem__)[:FALLBACK_NEAREST_COUNT]


def main() -> None:
    with SessionLocal() as db:
        rows = db.scalars(select(Station).options(selectinload(Station.chargers)).order_by(Station.source_id))
        stations = [
            {
                "id": str(s.id),
                "name": s.name,
                "lat": s.lat,
                "lon": s.lon,
                "chargers": len(s.chargers),
                "price_pence_per_kwh": s.price_pence_per_kwh,
                "arrival_rate_per_hour": s.arrival_rate_per_hour,
                "mean_service_minutes": s.mean_service_minutes,
            }
            for s in rows
            if s.chargers
        ]
    if not stations:
        raise SystemExit("No stations in the database. Run the ingest script first.")

    graph = get_road_graph()
    rng = np.random.default_rng(SEED)
    n_origins = ORIGINS_PER_SCENARIO * len(SCENARIOS)
    shape = (n_origins, len(stations))
    matrices = {
        name: np.full(shape, np.nan, dtype=np.float32)
        for name in ("osrm_km", "osrm_min", "dijkstra_km", "dijkstra_min")
    }
    origins = np.zeros((n_origins, 2))
    scenario_of = np.zeros(n_origins, dtype=np.int16)

    row = 0
    for scenario_index, scenario in enumerate(SCENARIOS.values()):
        for _ in range(ORIGINS_PER_SCENARIO):
            origin = draw_origin(scenario, rng)
            candidates = candidates_for(origin, stations)
            points = [(stations[i]["lat"], stations[i]["lon"]) for i in candidates]

            osrm = route_one_to_many(origin_lat=origin[0], origin_lon=origin[1], destinations=points)
            if osrm is None:
                raise SystemExit("OSRM is not responding. Start it with `docker compose up -d osrm`.")
            ours = graph.fastest_routes(origin, points)
            for i, o, d in zip(candidates, osrm, ours, strict=True):
                if np.isfinite(o.distance_km):
                    matrices["osrm_km"][row, i] = o.distance_km
                    matrices["osrm_min"][row, i] = o.duration_min
                if d is not None:
                    matrices["dijkstra_km"][row, i] = d.distance_km
                    matrices["dijkstra_min"][row, i] = d.duration_min

            origins[row] = origin
            scenario_of[row] = scenario_index
            row += 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "stations.json").write_text(json.dumps(stations, indent=1), encoding="utf-8")
    np.savez_compressed(DATA_DIR / "travel.npz", origins=origins, scenario=scenario_of, **matrices)
    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": SEED,
        "stations": len(stations),
        "chargers": sum(s["chargers"] for s in stations),
        "origins_per_scenario": ORIGINS_PER_SCENARIO,
        "scenarios": list(SCENARIOS),
        "candidate_rule": f"within {CANDIDATE_RADIUS_KM:g} km, else the {FALLBACK_NEAREST_COUNT} nearest",
        "osm_extract": "Geofabrik greater-london-260101.osm.pbf",
        "station_source": "OpenChargeMap API",
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
