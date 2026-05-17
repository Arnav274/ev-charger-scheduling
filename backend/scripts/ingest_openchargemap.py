import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

import requests
from sqlalchemy import text

from app.config import ARRIVAL_RATE_PER_HOUR_DEFAULT
from app.database import SessionLocal

CACHE_PATH = Path(__file__).parent / "cache" / "openchargemap_westminster_camden_sample.json"
MIN_STATIONS_REQUIRED = 50


def borough_from_lat_lon(lat: float, lon: float) -> str:
    # Coarse split for project scope labelling.
    if lat < 51.52:
        return "Westminster"
    return "Camden"


def fetch_openchargemap(
    live: bool,
    *,
    latitude: float = 51.52,
    longitude: float = -0.13,
    distance_km: float = 8.0,
    max_results: int = 500,
) -> list[dict]:
    if not live:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    # Default bounding area covers Westminster + Camden.
    params = {
        "output": "json",
        "countrycode": "GB",
        "latitude": latitude,
        "longitude": longitude,
        "distance": distance_km,
        "distanceunit": "KM",
        "maxresults": max_results,
    }
    headers = {
        "User-Agent": "uea-ev-dissertation/1.0 (educational project)",
        "Accept": "application/json",
    }
    api_key = (os.getenv("OPENCHARGEMAP_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENCHARGEMAP_API_KEY is missing or empty in this environment. "
            "Put OPENCHARGEMAP_API_KEY=... in the project .env next to docker-compose.yml, then recreate the backend "
            "so the container picks it up: docker compose up -d --force-recreate backend"
        )
    headers["X-API-Key"] = api_key

    response = requests.get(
        "https://api.openchargemap.io/v3/poi/",
        params=params,
        headers=headers,
        timeout=60,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "OpenChargeMap returned 403 Forbidden with X-API-Key set. "
            "Check the key is valid at https://openchargemap.org/site/developerinfo — "
            "or run without --live to use the cached sample dataset."
        )
    response.raise_for_status()
    return response.json()


def ingest(records: list[dict], *, enforce_min_stations: bool = True) -> None:
    db = SessionLocal()
    try:
        inserted_station_ids: set[str] = set()
        for rec in records:
            info = rec.get("AddressInfo", {})
            source_id = str(rec.get("ID"))
            if not source_id or "Latitude" not in info or "Longitude" not in info:
                continue
            lat = float(info["Latitude"])
            lon = float(info["Longitude"])
            borough = borough_from_lat_lon(lat, lon)
            chargers_count = int(rec.get("NumberOfPoints") or 1)

            station_id = db.execute(
                text(
                    """
                    INSERT INTO stations (
                        id, source, source_id, name, borough, address, lat, lon, location,
                        price_pence_per_kwh, arrival_rate_per_hour, mean_service_minutes, raw_json
                    )
                    VALUES (
                        :station_id, :source, :source_id, :name, :borough, :address, :lat, :lon,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                        :price, :arrival_rate, :service_min, CAST(:raw_json AS JSON)
                    )
                    ON CONFLICT (source_id) DO UPDATE SET
                      name = EXCLUDED.name,
                      borough = EXCLUDED.borough,
                      address = EXCLUDED.address,
                      lat = EXCLUDED.lat,
                      lon = EXCLUDED.lon,
                      location = EXCLUDED.location,
                      raw_json = EXCLUDED.raw_json
                    RETURNING id;
                    """
                ),
                {
                    "source": "openchargemap",
                    "station_id": str(uuid4()),
                    "source_id": source_id,
                    "name": info.get("Title", f"Station {source_id}"),
                    "borough": borough,
                    "address": info.get("AddressLine1"),
                    "lat": lat,
                    "lon": lon,
                    "price": 55.0,
                    "arrival_rate": ARRIVAL_RATE_PER_HOUR_DEFAULT,
                    "service_min": 40.0,
                    "raw_json": json.dumps(rec),
                },
            ).scalar_one()
            inserted_station_ids.add(str(station_id))

            # Reservations reference chargers; remove them before replacing charger rows.
            db.execute(
                text(
                    """
                    DELETE FROM reservations
                    WHERE charger_id IN (SELECT id FROM chargers WHERE station_id = :station_id)
                    """
                ),
                {"station_id": station_id},
            )
            db.execute(text("DELETE FROM chargers WHERE station_id = :station_id"), {"station_id": station_id})
            for idx in range(chargers_count):
                db.execute(
                    text(
                        """
                        INSERT INTO chargers (id, station_id, name, power_kw, connector_type)
                        VALUES (:charger_id, :station_id, :name, :power_kw, :connector_type)
                        """
                    ),
                    {
                        "charger_id": str(uuid4()),
                        "station_id": station_id,
                        "name": f"Charger {idx + 1}",
                        "power_kw": 22.0,
                        "connector_type": "Type2",
                    },
                )
        db.commit()
        # Dissertation-scale guard applies to live API pulls only; cached sample is intentionally tiny for offline dev.
        if enforce_min_stations:
            station_count = db.execute(text("SELECT COUNT(*) FROM stations WHERE source = 'openchargemap'")).scalar_one()
            if int(station_count) < MIN_STATIONS_REQUIRED:
                raise RuntimeError(
                    f"Only {station_count} OpenChargeMap stations in DB after ingest; require >= {MIN_STATIONS_REQUIRED}. "
                    "Increase --distance-km and/or --max-results, and ensure OPENCHARGEMAP_API_KEY is set for live ingestion."
                )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Fetch from OpenChargeMap API")
    parser.add_argument("--latitude", type=float, default=51.52, help="Center latitude for live fetch")
    parser.add_argument("--longitude", type=float, default=-0.13, help="Center longitude for live fetch")
    parser.add_argument("--distance-km", type=float, default=8.0, help="Search radius in KM for live fetch")
    parser.add_argument("--max-results", type=int, default=500, help="Max stations to request from API")
    args = parser.parse_args()
    ingest(
        fetch_openchargemap(
            live=args.live,
            latitude=args.latitude,
            longitude=args.longitude,
            distance_km=args.distance_km,
            max_results=args.max_results,
        ),
        enforce_min_stations=args.live,
    )
    print("Ingestion complete.")
