"""Load London charging stations from OpenChargeMap into the stations and chargers tables.

    docker compose exec backend python -m scripts.ingest_openchargemap --live

Without --live a two-station sample from scripts/cache is loaded instead, which
is enough to click around offline but not to run the experiments.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
from pathlib import Path

import requests
from sqlalchemy import text

from app.config import ARRIVAL_RATE_PER_HOUR_DEFAULT, MEAN_SERVICE_MINUTES_DEFAULT
from app.database import SessionLocal

CACHE_PATH = Path(__file__).parent / "cache" / "openchargemap_westminster_camden_sample.json"
API_URL = "https://api.openchargemap.io/v3/poi/"
MIN_STATIONS_REQUIRED = 50
DEFAULT_POWER_KW = 7.0  # the most common public AC rating in the UK
# Used for the offline sample, where there are no tariffs to take a median from.
FALLBACK_PRICE_PENCE = 55.0

# Community-submitted test entries turn up in the live data, e.g. a "QA Test
# Station" placed exactly on Charing Cross.
TEST_ENTRY = re.compile(r"\b(test|qa|dummy)\b", re.IGNORECASE)
PRICE_POUNDS_PER_KWH = re.compile(r"£\s*(\d+(?:\.\d+)?)\s*(?:/|per)\s*kwh", re.IGNORECASE)
PRICE_PENCE_PER_KWH = re.compile(r"(\d+(?:\.\d+)?)\s*p\s*(?:/|per)\s*kwh", re.IGNORECASE)


def is_usable(record: dict) -> bool:
    """False for test entries and for stations known not to be working."""
    info = record.get("AddressInfo") or {}
    if info.get("Latitude") is None or info.get("Longitude") is None:
        return False
    if any(TEST_ENTRY.search(info.get(field) or "") for field in ("Title", "AddressLine1")):
        return False
    if (record.get("StatusType") or {}).get("IsOperational") is False:
        return False
    return (record.get("SubmissionStatus") or {}).get("IsLive") is not False


def parse_price_pence_per_kwh(usage_cost: str | None) -> float | None:
    """Energy price in pence per kWh from OpenChargeMap's free-text tariff, if it states one.

    Standing charges and per-minute tariffs are ignored; the first per-kWh
    figure wins (for day/night tariffs that is the day rate).
    """
    if not usage_cost:
        return None
    if usage_cost.strip().lower().startswith("free"):
        return 0.0
    if match := PRICE_POUNDS_PER_KWH.search(usage_cost):
        return float(match.group(1)) * 100
    if match := PRICE_PENCE_PER_KWH.search(usage_cost):
        return float(match.group(1))
    return None


def max_power_kw(record: dict) -> float:
    powers = [c.get("PowerKW") for c in record.get("Connections") or []]
    return max((float(p) for p in powers if p), default=DEFAULT_POWER_KW)


def fetch(latitude: float, longitude: float, distance_km: float, max_results: int) -> list[dict]:
    api_key = (os.getenv("OPENCHARGEMAP_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit(
            "OPENCHARGEMAP_API_KEY is empty. Put it in .env next to docker-compose.yml, then "
            "recreate the backend so it picks it up: docker compose up -d --force-recreate backend"
        )
    response = requests.get(
        API_URL,
        params={
            "output": "json",
            "countrycode": "GB",
            "latitude": latitude,
            "longitude": longitude,
            "distance": distance_km,
            "distanceunit": "KM",
            "maxresults": max_results,
        },
        headers={
            "X-API-Key": api_key,
            "User-Agent": "ev-charger-scheduling/1.0 (+https://github.com/Arnav274/ev-charger-scheduling)",
        },
        timeout=60,
    )
    if response.status_code == 403:
        raise SystemExit("OpenChargeMap rejected the API key (403). Check it at openchargemap.org.")
    response.raise_for_status()
    return response.json()


def ingest(records: list[dict], *, prune: bool) -> int:
    usable = [r for r in records if is_usable(r)]
    prices = [p for r in usable if (p := parse_price_pence_per_kwh(r.get("UsageCost"))) is not None]
    fallback_price = statistics.median(prices) if prices else FALLBACK_PRICE_PENCE

    with SessionLocal() as db:
        kept_ids = []
        for record in usable:
            info = record["AddressInfo"]
            price = parse_price_pence_per_kwh(record.get("UsageCost"))
            station_id = db.execute(
                text(
                    """
                    INSERT INTO stations (
                        id, source, source_id, name, borough, address, lat, lon,
                        price_pence_per_kwh, arrival_rate_per_hour, mean_service_minutes, raw_json
                    )
                    VALUES (
                        gen_random_uuid(), 'openchargemap', :source_id, :name, :area, :address, :lat, :lon,
                        :price, :arrival_rate, :service_min, CAST(:raw_json AS JSON)
                    )
                    ON CONFLICT (source_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        borough = EXCLUDED.borough,
                        address = EXCLUDED.address,
                        lat = EXCLUDED.lat,
                        lon = EXCLUDED.lon,
                        price_pence_per_kwh = EXCLUDED.price_pence_per_kwh,
                        raw_json = EXCLUDED.raw_json
                    RETURNING id
                    """
                ),
                {
                    "source_id": str(record["ID"]),
                    "name": (info.get("Title") or f"Station {record['ID']}").strip(),
                    "area": (info.get("Town") or "").strip().title() or None,
                    "address": info.get("AddressLine1"),
                    "lat": float(info["Latitude"]),
                    "lon": float(info["Longitude"]),
                    "price": fallback_price if price is None else price,
                    "arrival_rate": ARRIVAL_RATE_PER_HOUR_DEFAULT,
                    "service_min": MEAN_SERVICE_MINUTES_DEFAULT,
                    "raw_json": json.dumps(record),
                },
            ).scalar_one()
            kept_ids.append(station_id)

            # Chargers are rebuilt from the latest record, which drops their bookings.
            db.execute(
                text(
                    "DELETE FROM reservations WHERE charger_id IN "
                    "(SELECT id FROM chargers WHERE station_id = :sid)"
                ),
                {"sid": station_id},
            )
            db.execute(text("DELETE FROM chargers WHERE station_id = :sid"), {"sid": station_id})
            power = max_power_kw(record)
            for i in range(int(record.get("NumberOfPoints") or 1)):
                db.execute(
                    text(
                        "INSERT INTO chargers (id, station_id, name, power_kw, connector_type) "
                        "VALUES (gen_random_uuid(), :sid, :name, :power, 'Type2')"
                    ),
                    {"sid": station_id, "name": f"Charger {i + 1}", "power": power},
                )

        if prune:
            # Stations that have left OpenChargeMap, or are now filtered out, go too.
            stale = (
                "SELECT id FROM stations "
                "WHERE source = 'openchargemap' AND NOT (id = ANY(CAST(:kept AS uuid[])))"
            )
            params = {"kept": kept_ids}
            db.execute(
                text(
                    "DELETE FROM reservations WHERE charger_id IN "
                    f"(SELECT id FROM chargers WHERE station_id IN ({stale}))"
                ),
                params,
            )
            db.execute(text(f"DELETE FROM chargers WHERE station_id IN ({stale})"), params)
            db.execute(text(f"DELETE FROM stations WHERE id IN ({stale})"), params)
        db.commit()

    print(
        f"Loaded {len(usable)} of {len(records)} stations ({len(records) - len(usable)} test or "
        f"non-operational entries skipped). {len(prices)} had a per-kWh tariff; the rest use the "
        f"median, {fallback_price:.0f}p/kWh."
    )
    return len(usable)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load charging stations from OpenChargeMap.")
    parser.add_argument("--live", action="store_true", help="fetch from the OpenChargeMap API")
    parser.add_argument("--latitude", type=float, default=51.52)
    parser.add_argument("--longitude", type=float, default=-0.13)
    parser.add_argument("--distance-km", type=float, default=8.0)
    parser.add_argument("--max-results", type=int, default=500)
    args = parser.parse_args()

    if not args.live:
        ingest(json.loads(CACHE_PATH.read_text(encoding="utf-8")), prune=False)
        return
    loaded = ingest(fetch(args.latitude, args.longitude, args.distance_km, args.max_results), prune=True)
    if loaded < MIN_STATIONS_REQUIRED:
        raise SystemExit(f"Only {loaded} usable stations; widen --distance-km or raise --max-results.")


if __name__ == "__main__":
    main()
