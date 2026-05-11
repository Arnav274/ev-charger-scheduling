import json
import uuid
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.algorithms import RecommendationContext, STRATEGIES, haversine_km
from app.auth_deps import get_current_user_id
from app.auth_utils import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models import Charger, Reservation, Station, User
from app.queueing import erlang_c_wait_minutes
from app.schemas import (
    ExperimentSummaryResponse,
    NearbyStationOut,
    RecommendationOut,
    RecommendationRequest,
    ReservationCreate,
    ReservationOut,
    StationDetailOut,
    Token,
    UserRegister,
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

    max_distance = max(haversine_km(payload.origin_lat, payload.origin_lon, s.lat, s.lon) for s in candidates) or 1.0
    max_wait = (
        max(
            erlang_c_wait_minutes(s.arrival_rate_per_hour, s.mean_service_minutes, max(1, len(s.chargers)))
            for s in candidates
        )
        or 1.0
    )
    max_cost = max(s.price_pence_per_kwh for s in candidates) or 1.0
    max_vals = {"distance": max_distance, "wait": max_wait, "cost": max_cost}
    ctx = RecommendationContext(payload.origin_lat, payload.origin_lon, payload.weights)

    ranked = sorted(candidates, key=lambda s: strategy.score(s, ctx, max_vals))[: payload.top_k]
    return [
        RecommendationOut(
            station_id=s.id,
            station_name=s.name,
            score=strategy.score(s, ctx, max_vals),
            distance_km=haversine_km(payload.origin_lat, payload.origin_lon, s.lat, s.lon),
            predicted_wait_min=erlang_c_wait_minutes(
                s.arrival_rate_per_hour, s.mean_service_minutes, max(1, len(s.chargers))
            ),
            price_pence_per_kwh=s.price_pence_per_kwh,
        )
        for s in ranked
    ]
