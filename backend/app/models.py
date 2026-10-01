import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, Float, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base



class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )




class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    make_model: Mapped[str] = mapped_column(String(120), nullable=False)
    battery_kwh: Mapped[float] = mapped_column(Float, nullable=False)


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), default="openchargemap", nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    borough: Mapped[str] = mapped_column(String(80), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    price_pence_per_kwh: Mapped[float] = mapped_column(Float, default=55.0, nullable=False)
    # M/M/c queueing parameters: λ (arrivals/hour) and 1/μ (mean service time).
    # Defaults: 0.75 arrivals/hr and 40 min/session are calibrated from DfT/Zapmap
    # data and used across all Erlang-C wait calculations (see queueing.py).
    arrival_rate_per_hour: Mapped[float] = mapped_column(Float, default=0.75, nullable=False)
    mean_service_minutes: Mapped[float] = mapped_column(Float, default=40.0, nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    chargers: Mapped[list["Charger"]] = relationship(back_populates="station", cascade="all, delete-orphan")




class Charger(Base):
    __tablename__ = "chargers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    power_kw: Mapped[float] = mapped_column(Float, default=22.0, nullable=False)  # 22 kW = typical UK Type 2 fast charger
    connector_type: Mapped[str] = mapped_column(String(80), default="Type2", nullable=False)

    station: Mapped["Station"] = relationship(back_populates="chargers")
    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="charger", cascade="all, delete-orphan"
    )




class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    charger_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chargers.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    charger: Mapped["Charger"] = relationship(back_populates="reservations")
