from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class NearbyStationOut(BaseModel):
    id: UUID
    name: str
    borough: str | None
    lat: float
    lon: float
    price_pence_per_kwh: float
    distance_m: float


class ChargerOut(BaseModel):
    id: UUID
    name: str
    power_kw: float
    connector_type: str


class StationDetailOut(BaseModel):
    id: UUID
    name: str
    borough: str | None
    address: str | None
    lat: float
    lon: float
    price_pence_per_kwh: float
    chargers: list[ChargerOut]


class ReservationCreate(BaseModel):
    charger_id: UUID
    start_time: datetime
    end_time: datetime


class ReservationOut(BaseModel):
    id: UUID
    charger_id: UUID
    user_id: UUID
    start_time: datetime
    end_time: datetime


class RecommendationRequest(BaseModel):
    origin_lat: float
    origin_lon: float
    radius_km: float = Field(default=5.0, gt=0)
    algorithm: str = Field(default="queue_aware")
    weights: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)
    top_k: int = 5


class RecommendationOut(BaseModel):
    station_id: UUID
    station_name: str
    score: float
    distance_km: float
    predicted_wait_min: float
    price_pence_per_kwh: float


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ExperimentSummaryResponse(BaseModel):
    rows: list[dict]
