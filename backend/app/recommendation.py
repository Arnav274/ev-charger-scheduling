"""Builds ranked station recommendations for a driver.

The endpoint gathers everything a strategy might need up front (candidate
stations, road travel, reservations in each station's arrival window and
current occupancy) in a fixed number of queries, then hands the ranking to the
selected strategy.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.algorithms import STRATEGIES, RecommendationContext, StationInfo, Travel
from app.geo import haversine_km
from app.models import Charger, Reservation, Station
from app.predictive_queueing import ReservationInterval, booked_during_arrival, ensure_utc
from app.routing_osrm import route_one_to_many
from app.schemas import RecommendationOut, RecommendationRequest

# Used when no station lies inside the requested radius, so the driver still
# gets the closest options rather than an empty list.
FALLBACK_NEAREST_COUNT = 25
# Average London driving speed assumed when OSRM is unreachable.
FALLBACK_SPEED_KMH = 25.0


def _uuids(ids: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(i) for i in ids]


def load_candidates(db: Session, lat: float, lon: float, radius_km: float) -> list[StationInfo]:
    point = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography"
    params = {"lat": lat, "lon": lon}
    ids = (
        db.execute(
            text(f"SELECT id FROM stations WHERE ST_DWithin(location, {point}, :radius_m)"),
            {**params, "radius_m": radius_km * 1000},
        )
        .scalars()
        .all()
    )
    if not ids:
        ids = (
            db.execute(
                text(f"SELECT id FROM stations ORDER BY location <-> {point} LIMIT :n"),
                {**params, "n": FALLBACK_NEAREST_COUNT},
            )
            .scalars()
            .all()
        )
    if not ids:
        return []
    stations = db.scalars(select(Station).options(selectinload(Station.chargers)).where(Station.id.in_(ids)))
    return [StationInfo.from_model(s) for s in stations if s.chargers]


def road_travel(lat: float, lon: float, stations: list[StationInfo]) -> dict[str, Travel]:
    metrics = route_one_to_many(
        origin_lat=lat, origin_lon=lon, destinations=[(s.lat, s.lon) for s in stations]
    )
    if metrics is None:
        travel = {}
        for s in stations:
            km = haversine_km(lat, lon, s.lat, s.lon)
            travel[s.id] = Travel(km, km / FALLBACK_SPEED_KMH * 60.0)
        return travel
    return {s.id: Travel(m.distance_km, m.duration_min) for s, m in zip(stations, metrics, strict=True)}


def reservations_by_station(
    db: Session, station_ids: list[str], start: datetime, end: datetime
) -> dict[str, list[ReservationInterval]]:
    rows = db.execute(
        select(Charger.station_id, Reservation.start_time, Reservation.end_time)
        .join(Reservation, Reservation.charger_id == Charger.id)
        .where(
            Charger.station_id.in_(_uuids(station_ids)),
            Reservation.start_time < end,
            Reservation.end_time > start,
        )
    )
    grouped: dict[str, list[ReservationInterval]] = defaultdict(list)
    for station_id, start_time, end_time in rows:
        grouped[str(station_id)].append(ReservationInterval(start_time, end_time))
    return grouped


def occupancy_by_station(db: Session, station_ids: list[str], now: datetime) -> dict[str, int]:
    rows = db.execute(
        select(Charger.station_id, func.count())
        .join(Reservation, Reservation.charger_id == Charger.id)
        .where(
            Charger.station_id.in_(_uuids(station_ids)),
            Reservation.start_time <= now,
            Reservation.end_time > now,
        )
        .group_by(Charger.station_id)
    )
    return {str(station_id): count for station_id, count in rows}


def recommend(db: Session, req: RecommendationRequest, now: datetime) -> list[RecommendationOut]:
    strategy = STRATEGIES[req.algorithm]
    stations = load_candidates(db, req.origin_lat, req.origin_lon, req.radius_km)
    if not stations:
        return []

    travel = road_travel(req.origin_lat, req.origin_lon, stations)
    # OSRM reports unroutable pairs (e.g. an island of the road network) as infinite.
    stations = [s for s in stations if math.isfinite(travel[s.id].distance_km)]
    if not stations:
        return []

    departure = ensure_utc(req.departure_time) if req.departure_time else now
    window = timedelta(minutes=req.arrival_window_minutes)
    arrival_at = {
        s.id: ensure_utc(req.arrival_time_target)
        if req.arrival_time_target
        else departure + timedelta(minutes=travel[s.id].duration_min)
        for s in stations
    }

    ids = [s.id for s in stations]
    reserved = {}
    if strategy.uses_reservations:
        bookings = reservations_by_station(
            db, ids, min(arrival_at.values()), max(arrival_at.values()) + window
        )
        reserved = {
            s.id: booked_during_arrival(bookings.get(s.id, []), arrival_at[s.id], window) for s in stations
        }
    occupancy = occupancy_by_station(db, ids, now)

    ctx = RecommendationContext(
        origin_lat=req.origin_lat,
        origin_lon=req.origin_lon,
        travel=travel,
        reserved_by_station=reserved,
        weights=req.weights,
        battery_level_percent=req.battery_level_percent,
        battery_capacity_kwh=req.battery_capacity_kwh,
    )
    results = []
    for r in strategy.rank(stations, ctx)[: req.top_k]:
        # Dijkstra reports the route it found itself; other strategies use OSRM's.
        route = r.travel or travel[r.station.id]
        arrival = arrival_at[r.station.id]
        if r.travel and not req.arrival_time_target:
            arrival = departure + timedelta(minutes=route.duration_min)
        results.append(
            RecommendationOut(
                station_id=r.station.id,
                station_name=r.station.name,
                lat=r.station.lat,
                lon=r.station.lon,
                score=r.score,
                travel_distance_km=route.distance_km,
                travel_time_min=route.duration_min,
                arrival_time_est=arrival,
                predicted_wait_min=r.prediction.wait_min,
                probability_of_delay=r.prediction.probability_of_delay,
                price_pence_per_kwh=r.station.price_pence_per_kwh,
                current_occupancy=occupancy.get(r.station.id, 0),
            )
        )
    return results
