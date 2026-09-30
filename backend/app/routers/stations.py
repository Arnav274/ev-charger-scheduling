import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Charger, Reservation, Station
from app.predictive_queueing import ensure_utc
from app.schemas import ChargerOut, NearbyStationOut, SlotRequest, SlotSuggestion, StationDetailOut

router = APIRouter(prefix="/stations", tags=["stations"])

SLOT_STEP = timedelta(minutes=30)
SLOT_SEARCH_HORIZON = timedelta(hours=4)


@router.get("/nearby", response_model=list[NearbyStationOut])
def nearby_stations(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=5.0, gt=0, le=50),
    db: Session = Depends(get_db),
) -> list[NearbyStationOut]:
    rows = db.execute(
        text(
            """
            SELECT id, name, borough, lat, lon, price_pence_per_kwh,
                   ST_Distance(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS distance_m
            FROM stations
            WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_m)
            ORDER BY distance_m
            """
        ),
        {"lat": lat, "lon": lon, "radius_m": radius_km * 1000},
    ).all()
    return [NearbyStationOut.model_validate(row, from_attributes=True) for row in rows]


def _get_station(db: Session, station_id: uuid.UUID) -> Station:
    station = db.scalar(
        select(Station).options(selectinload(Station.chargers)).where(Station.id == station_id)
    )
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


@router.get("/{station_id}", response_model=StationDetailOut)
def station_detail(station_id: uuid.UUID, db: Session = Depends(get_db)) -> StationDetailOut:
    station = _get_station(db, station_id)
    return StationDetailOut(
        id=station.id,
        name=station.name,
        borough=station.borough,
        address=station.address,
        lat=station.lat,
        lon=station.lon,
        price_pence_per_kwh=station.price_pence_per_kwh,
        chargers=[ChargerOut.model_validate(c, from_attributes=True) for c in station.chargers],
    )


def next_slot_boundary(dt: datetime) -> datetime:
    """Earliest half-hour boundary at or after dt."""
    floored = dt.replace(minute=dt.minute - dt.minute % 30, second=0, microsecond=0)
    return floored if floored == dt else floored + SLOT_STEP


@router.post("/{station_id}/suggest-slot", response_model=list[SlotSuggestion])
def suggest_slot(
    station_id: uuid.UUID, payload: SlotRequest, db: Session = Depends(get_db)
) -> list[SlotSuggestion]:
    """Earliest free half-hour-aligned slot on each charger within four hours of the desired arrival."""
    station = _get_station(db, station_id)
    chargers = station.chargers
    if payload.charger_id is not None:
        chargers = [c for c in chargers if c.id == payload.charger_id]

    desired = ensure_utc(payload.desired_arrival)
    # Never offer a slot that has already started, whatever time was asked for.
    earliest = max(desired, datetime.now(UTC))
    horizon_end = earliest + SLOT_SEARCH_HORIZON
    duration = timedelta(minutes=payload.duration_minutes)

    rows = db.execute(
        select(Reservation.charger_id, Reservation.start_time, Reservation.end_time)
        .join(Charger, Charger.id == Reservation.charger_id)
        .where(
            Charger.station_id == station.id,
            Reservation.start_time < horizon_end,
            Reservation.end_time > earliest,
        )
    )
    booked: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    for charger_id, start, end in rows:
        booked[str(charger_id)].append((ensure_utc(start), ensure_utc(end)))

    suggestions = []
    for charger in chargers:
        existing = booked[str(charger.id)]
        start = next_slot_boundary(earliest)
        while start + duration <= horizon_end:
            end = start + duration
            if not any(b_start < end and b_end > start for b_start, b_end in existing):
                suggestions.append(
                    SlotSuggestion(
                        charger_id=charger.id,
                        suggested_start=start,
                        suggested_end=end,
                        wait_from_desired_minutes=(start - desired).total_seconds() / 60.0,
                    )
                )
                break
            start += SLOT_STEP

    suggestions.sort(key=lambda s: s.wait_from_desired_minutes)
    return suggestions
