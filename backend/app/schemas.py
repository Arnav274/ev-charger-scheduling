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


class ReservationDetailOut(BaseModel):
    id: UUID
    charger_id: UUID
    user_id: UUID
    start_time: datetime
    end_time: datetime
    station_name: str
    charger_name: str


class RecommendationRequest(BaseModel):
    origin_lat: float
    origin_lon: float
    radius_km: float = Field(default=5.0, gt=0)
    algorithm: str = "queue_aware"
    weights: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)
    top_k: int = 5
    departure_time: datetime | None = None
    arrival_time_target: datetime | None = None
    arrival_window_minutes: int = Field(default=15, ge=1, le=240)
    battery_level_percent: float | None = None  # 0–100
    battery_capacity_kwh: float | None = None


class RecommendationOut(BaseModel):
    station_id: UUID
    station_name: str
    score: float
    travel_distance_km: float
    travel_time_min: float
    arrival_time_est: datetime
    predicted_wait_min: float
    probability_of_delay: float
    price_pence_per_kwh: float
    current_occupancy: int


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ExperimentSummaryResponse(BaseModel):
    rows: list[dict]


class SlotRequest(BaseModel):
    desired_arrival: datetime
    duration_minutes: int = Field(gt=0, le=480)
    charger_id: UUID | None = None


class SlotSuggestion(BaseModel):
    charger_id: UUID
    suggested_start: datetime
    suggested_end: datetime
    wait_from_desired_minutes: float


class VehicleCreate(BaseModel):
    make_model: str = Field(max_length=120)
    battery_kwh: float = Field(gt=0)


class VehicleOut(BaseModel):
    id: UUID
    make_model: str
    battery_kwh: float
