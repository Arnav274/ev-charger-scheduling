import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.algorithms import DijkstraStrategy, RecommendationContext, STRATEGIES, haversine_km
from app.auth_deps import get_current_user_id
from app.auth_utils import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models import Charger, Reservation, Station, User, Vehicle
from datetime import datetime, timedelta, timezone

from app.predictive_queueing import ReservationInterval, arrival_window, count_starts_in_window, ensure_utc, max_overlapping
from app.queueing import erlang_c_probability_of_delay, erlang_c_wait_minutes
from app.routing_osrm import route_one_to_many
from app.schemas import (
    ExperimentSummaryResponse,
    NearbyStationOut,
    RecommendationOut,
    RecommendationRequest,
    ReservationCreate,
    ReservationOut,
    SlotRequest,
    SlotSuggestion,
    StationDetailOut,
    Token,
    UserRegister,
    VehicleCreate,
    VehicleOut,
)

app = FastAPI(title="EV Reservation Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stations/nearby", response_model=list[NearbyStationOut])
def nearby_stations(lat: float, lon: float, radius_km: float = 5.0, db: Session = Depends(get_db)) -> list[NearbyStationOut]:
    radius_m = radius_km * 1000
    rows = db.execute(
        text(
            """
            SELECT
                id, name, borough, lat, lon, price_pence_per_kwh,
                ST_Distance(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS distance_m
            FROM stations
            WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_m)
            ORDER BY distance_m ASC;
            """
        ),
        {"lat": lat, "lon": lon, "radius_m": radius_m},
    ).all()
    return [
        NearbyStationOut(
            id=row.id,
            name=row.name,
            borough=row.borough,
            lat=row.lat,
            lon=row.lon,
            price_pence_per_kwh=row.price_pence_per_kwh,
            distance_m=float(row.distance_m),
        )
        for row in rows
    ]


@app.get("/stations/{station_id}", response_model=StationDetailOut)
def station_detail(station_id: str, db: Session = Depends(get_db)) -> StationDetailOut:
    station = (
        db.query(Station)
        .options(joinedload(Station.chargers))
        .filter(Station.id == station_id)
        .first()
    )
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return StationDetailOut(
        id=station.id,
        name=station.name,
        borough=station.borough,
        address=station.address,
        lat=station.lat,
        lon=station.lon,
        price_pence_per_kwh=station.price_pence_per_kwh,
        chargers=[
            {
                "id": c.id,
                "name": c.name,
                "power_kw": c.power_kw,
                "connector_type": c.connector_type,
            }
            for c in station.chargers
        ],
    )


def _next_30min_aligned(dt: datetime) -> datetime:
    """Return the earliest 30-minute-boundary datetime >= dt (seconds/µs stripped)."""
    clean = dt.replace(second=0, microsecond=0)
    minutes = clean.minute
    if minutes % 30 == 0 and dt.second == 0 and dt.microsecond == 0:
        return clean
    return clean + timedelta(minutes=30 - (minutes % 30))


@app.post("/stations/{station_id}/suggest-slot", response_model=list[SlotSuggestion])
def suggest_slot(station_id: str, payload: SlotRequest, db: Session = Depends(get_db)) -> list[SlotSuggestion]:
    station = (
        db.query(Station)
        .options(joinedload(Station.chargers))
        .filter(Station.id == station_id)
        .first()
    )
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    desired = ensure_utc(payload.desired_arrival)
    window_end = desired + timedelta(hours=4)
    duration = timedelta(minutes=payload.duration_minutes)

    chargers = station.chargers
    if payload.charger_id is not None:
        chargers = [c for c in chargers if c.id == payload.charger_id]

    rows = db.execute(
        text(
            """
            SELECT r.charger_id, r.start_time, r.end_time
            FROM reservations r
            JOIN chargers c ON c.id = r.charger_id
            WHERE c.station_id = :station_id
              AND r.start_time < :window_end
              AND r.end_time   > :desired
            """
        ),
        {"station_id": station_id, "window_end": window_end, "desired": desired},
    ).all()

    reservations_by_charger: dict[str, list] = defaultdict(list)
    for row in rows:
        reservations_by_charger[str(row.charger_id)].append(
            (ensure_utc(row.start_time), ensure_utc(row.end_time))
        )

    suggestions: list[SlotSuggestion] = []
    for charger in chargers:
        cid = str(charger.id)
        existing = reservations_by_charger.get(cid, [])
        candidate = _next_30min_aligned(desired)
        while candidate + duration <= window_end:
            slot_end = candidate + duration
            if not any(r_start < slot_end and r_end > candidate for r_start, r_end in existing):
                wait_min = (candidate - desired).total_seconds() / 60.0
                suggestions.append(
                    SlotSuggestion(
                        charger_id=charger.id,
                        suggested_start=candidate,
                        suggested_end=slot_end,
                        wait_from_desired_minutes=wait_min,
                    )
                )
                break
            candidate += timedelta(minutes=30)

    suggestions.sort(key=lambda s: s.wait_from_desired_minutes)
    return suggestions


@app.post("/auth/register", response_model=Token, status_code=201)
def register_user(body: UserRegister, db: Session = Depends(get_db)) -> Token:
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_access_token(user.id))


@app.post("/auth/login", response_model=Token)
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
) -> Token:
    user = db.query(User).filter(User.email == form_data.username.strip().lower()).first()
    if not user or not user.password_hash or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return Token(access_token=create_access_token(user.id))


@app.post("/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(
    payload: VehicleCreate,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> VehicleOut:
    vehicle = Vehicle(user_id=user_id, make_model=payload.make_model, battery_kwh=payload.battery_kwh)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return VehicleOut(id=vehicle.id, make_model=vehicle.make_model, battery_kwh=vehicle.battery_kwh)


@app.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> list[VehicleOut]:
    vehicles = db.query(Vehicle).filter(Vehicle.user_id == user_id).all()
    return [VehicleOut(id=v.id, make_model=v.make_model, battery_kwh=v.battery_kwh) for v in vehicles]


EXPERIMENT_OUT = Path(__file__).resolve().parent.parent / "experiments" / "outputs"


@app.get("/stats/experiment-summary", response_model=ExperimentSummaryResponse)
def experiment_summary_csv() -> ExperimentSummaryResponse:
    path = EXPERIMENT_OUT / "summary_ci.csv"
    if not path.is_file():
        return ExperimentSummaryResponse(rows=[])
    df = pd.read_csv(path)
    records = json.loads(df.to_json(orient="records"))
    return ExperimentSummaryResponse(rows=records)


@app.post("/reservations", response_model=ReservationOut, status_code=201)
def create_reservation(
    payload: ReservationCreate,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> ReservationOut:
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    reservation = Reservation(
        charger_id=payload.charger_id,
        user_id=user_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    db.add(reservation)
    try:
        db.commit()
        db.refresh(reservation)
    except IntegrityError as exc:
        db.rollback()
        if "exclude_overlapping_reservations" in str(exc.orig):
            raise HTTPException(status_code=409, detail="Overlapping reservation") from exc
        raise HTTPException(status_code=400, detail="Reservation creation failed") from exc
    return ReservationOut(
        id=reservation.id,
        charger_id=reservation.charger_id,
        user_id=reservation.user_id,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
    )


@app.post("/recommendations", response_model=list[RecommendationOut])
def recommend(payload: RecommendationRequest, db: Session = Depends(get_db)) -> list[RecommendationOut]:
    strategy = STRATEGIES.get(payload.algorithm)
    if strategy is None:
        raise HTTPException(status_code=400, detail=f"Unknown algorithm '{payload.algorithm}'")

    stations = (
        db.query(Station)
        .options(joinedload(Station.chargers))
        .all()
    )
    if not stations:
        return []

    in_radius = [
        s
        for s in stations
        if haversine_km(payload.origin_lat, payload.origin_lon, s.lat, s.lon) <= payload.radius_km
    ]
    candidates = in_radius if in_radius else stations

    departure_time = ensure_utc(payload.departure_time) if payload.departure_time else datetime.now(timezone.utc)

    # Routing: one origin -> many stations (OSRM table). Fallback to haversine if OSRM unavailable.
    travel_metrics = route_one_to_many(
        origin_lat=payload.origin_lat,
        origin_lon=payload.origin_lon,
        destinations=[(s.lat, s.lon) for s in candidates],
    )
    travel_by_station: dict[str, tuple[float, float]] = {}
    if travel_metrics is None:
        for s in candidates:
            d_km = haversine_km(payload.origin_lat, payload.origin_lon, s.lat, s.lon)
            # Conservative fallback (used only when OSRM unreachable)
            t_min = (d_km / 25.0) * 60.0
            travel_by_station[str(s.id)] = (d_km, t_min)
    else:
        for s, m in zip(candidates, travel_metrics, strict=False):
            travel_by_station[str(s.id)] = (m.distance_km, m.duration_min)

    # Query future reservations for each station in the user's arrival window and derive future congestion deltas.
    future_reserved_parallel_by_station: dict[str, int] = {}
    future_reservation_starts_by_station: dict[str, int] = {}

    for s in candidates:
        distance_km, travel_time_min = travel_by_station[str(s.id)]
        arrival_est, window_start, window_end = arrival_window(
            departure_time=departure_time,
            travel_time_min=travel_time_min,
            arrival_window_minutes=payload.arrival_window_minutes,
        )
        if payload.arrival_time_target is not None:
            arrival_est = ensure_utc(payload.arrival_time_target)
            window_start = arrival_est
            window_end = arrival_est + timedelta(minutes=int(payload.arrival_window_minutes))

        rows = db.execute(
            text(
                """
                SELECT r.start_time, r.end_time
                FROM reservations r
                JOIN chargers c ON c.id = r.charger_id
                WHERE c.station_id = :station_id
                  AND r.start_time < :window_end
                  AND r.end_time > :window_start
                """
            ),
            {"station_id": str(s.id), "window_start": window_start, "window_end": window_end},
        ).all()

        intervals = [ReservationInterval(start_time=row.start_time, end_time=row.end_time) for row in rows]
        future_reserved_parallel_by_station[str(s.id)] = max_overlapping(intervals)
        future_reservation_starts_by_station[str(s.id)] = count_starts_in_window(
            intervals, window_start=window_start, window_end=window_end
        )

    now_utc = datetime.now(timezone.utc)
    current_occupancy_by_station: dict[str, int] = {}
    for s in candidates:
        row = db.execute(
            text(
                """
                SELECT COUNT(*) AS occupancy
                FROM reservations r
                JOIN chargers c ON c.id = r.charger_id
                WHERE c.station_id = :station_id
                  AND r.start_time <= :now
                  AND r.end_time > :now
                """
            ),
            {"station_id": str(s.id), "now": now_utc},
        ).one()
        current_occupancy_by_station[str(s.id)] = int(row.occupancy)

    max_distance = max(travel_by_station[str(s.id)][0] for s in candidates) or 1.0

    max_wait_static = (
        max(
            erlang_c_wait_minutes(
                s.arrival_rate_per_hour,
                s.mean_service_minutes,
                max(1, len(s.chargers)),
            )
            for s in candidates
        )
        or 1.0
    )

    _window_hours = max(1, int(payload.arrival_window_minutes)) / 60.0
    max_wait_predictive = (
        max(
            erlang_c_wait_minutes(
                arrival_rate_per_hour=s.arrival_rate_per_hour
                + future_reservation_starts_by_station.get(str(s.id), 0) / _window_hours,
                mean_service_minutes=s.mean_service_minutes,
                c=max(
                    1,
                    len(s.chargers)
                    - future_reserved_parallel_by_station.get(str(s.id), 0)
                    - current_occupancy_by_station.get(str(s.id), 0),
                ),
            )
            for s in candidates
        )
        or 1.0
    )

    _predictive_algorithms = {"queue_aware", "range_aware", "dijkstra"}
    max_wait = max_wait_predictive if payload.algorithm in _predictive_algorithms else max_wait_static

    max_cost = max(s.price_pence_per_kwh for s in candidates) or 1.0
    max_vals = {"distance": max_distance, "wait": max_wait, "cost": max_cost}
    ctx = RecommendationContext(
        payload.origin_lat,
        payload.origin_lon,
        payload.weights,
        arrival_window_minutes=payload.arrival_window_minutes,
        future_reserved_parallel_by_station=future_reserved_parallel_by_station,
        future_reservation_starts_by_station=future_reservation_starts_by_station,
        travel_by_station=travel_by_station,
        current_occupancy_by_station=current_occupancy_by_station,
        battery_level_percent=payload.battery_level_percent,
        battery_capacity_kwh=payload.battery_capacity_kwh,
    )

    pre_computed_dijkstra: dict[str, float] | None = None
    if isinstance(strategy, DijkstraStrategy):
        pre_computed_dijkstra = strategy.rank_all(candidates, ctx)

    def _score(s: Station) -> float:
        if pre_computed_dijkstra is not None:
            return strategy.score(s, ctx, max_vals, pre_computed_dijkstra[str(s.id)])
        return strategy.score(s, ctx, max_vals)

    ranked = sorted(candidates, key=_score)[: payload.top_k]
    return [
        RecommendationOut(
            station_id=s.id,
            station_name=s.name,
            score=_score(s),
            travel_distance_km=travel_by_station[str(s.id)][0],
            travel_time_min=travel_by_station[str(s.id)][1],
            arrival_time_est=(
                ensure_utc(payload.arrival_time_target)
                if payload.arrival_time_target is not None
                else arrival_window(
                    departure_time=departure_time,
                    travel_time_min=travel_by_station[str(s.id)][1],
                    arrival_window_minutes=payload.arrival_window_minutes,
                )[0]
            ),
            predicted_wait_min=(
                erlang_c_wait_minutes(
                    arrival_rate_per_hour=s.arrival_rate_per_hour
                    + (
                        future_reservation_starts_by_station.get(str(s.id), 0)
                        / (max(1, payload.arrival_window_minutes) / 60.0)
                    ),
                    mean_service_minutes=s.mean_service_minutes,
                    c=max(
                        1,
                        len(s.chargers)
                        - future_reserved_parallel_by_station.get(str(s.id), 0)
                        - current_occupancy_by_station.get(str(s.id), 0),
                    ),
                )
                if payload.algorithm == "queue_aware"
                else erlang_c_wait_minutes(s.arrival_rate_per_hour, s.mean_service_minutes, max(1, len(s.chargers)))
            ),
            probability_of_delay=(
                erlang_c_probability_of_delay(
                    arrival_rate_per_hour=s.arrival_rate_per_hour
                    + (
                        future_reservation_starts_by_station.get(str(s.id), 0)
                        / (max(1, payload.arrival_window_minutes) / 60.0)
                    ),
                    service_rate_per_hour=60.0 / s.mean_service_minutes,
                    c=max(
                        1,
                        len(s.chargers)
                        - future_reserved_parallel_by_station.get(str(s.id), 0)
                        - current_occupancy_by_station.get(str(s.id), 0),
                    ),
                )
                if payload.algorithm == "queue_aware"
                else erlang_c_probability_of_delay(
                    arrival_rate_per_hour=s.arrival_rate_per_hour,
                    service_rate_per_hour=60.0 / s.mean_service_minutes,
                    c=max(1, len(s.chargers)),
                )
            ),
            price_pence_per_kwh=s.price_pence_per_kwh,
            current_occupancy=current_occupancy_by_station.get(str(s.id), 0),
        )
        for s in ranked
    ]
