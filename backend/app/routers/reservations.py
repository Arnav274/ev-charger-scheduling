import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth_deps import get_current_user_id
from app.config import MAX_ADVANCE, MAX_BOOKING, MAX_UPCOMING_PER_USER
from app.database import get_db
from app.models import Charger, Reservation, Station
from app.predictive_queueing import ensure_utc
from app.schemas import ReservationCreate, ReservationDetailOut, ReservationOut

router = APIRouter(prefix="/reservations", tags=["reservations"])

# Allowance for clock differences between the browser and the server.
CLOCK_SKEW = timedelta(minutes=5)


@router.post("", response_model=ReservationOut, status_code=201)
def create_reservation(
    payload: ReservationCreate,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> ReservationOut:
    start, end = ensure_utc(payload.start_time), ensure_utc(payload.end_time)
    now = datetime.now(UTC)
    if end <= start:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")
    if start < now - CLOCK_SKEW or end <= now:
        raise HTTPException(status_code=400, detail="Bookings must start in the future")
    if start > now + MAX_ADVANCE:
        raise HTTPException(
            status_code=400, detail=f"Bookings can be made at most {MAX_ADVANCE.days} days ahead"
        )
    if end - start > MAX_BOOKING:
        raise HTTPException(
            status_code=400, detail=f"Bookings can last at most {MAX_BOOKING.total_seconds() / 3600:g} hours"
        )
    if db.get(Charger, payload.charger_id) is None:
        raise HTTPException(status_code=404, detail="Charger not found")
    # Serialise this user's bookings for the rest of the transaction, so parallel
    # requests cannot all pass the count below before any of them commits.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:user_id, 0))"), {"user_id": str(user_id)})
    upcoming = db.scalar(
        select(func.count()).where(Reservation.user_id == user_id, Reservation.end_time > now)
    )
    if upcoming >= MAX_UPCOMING_PER_USER:
        raise HTTPException(
            status_code=409, detail=f"You already have {MAX_UPCOMING_PER_USER} upcoming bookings"
        )

    reservation = Reservation(charger_id=payload.charger_id, user_id=user_id, start_time=start, end_time=end)
    db.add(reservation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # A GiST exclusion constraint in the database rules out double booking,
        # including two requests racing for the same slot.
        if "exclude_overlapping_reservations" in str(exc.orig):
            raise HTTPException(status_code=409, detail="Overlapping reservation") from exc
        raise HTTPException(status_code=400, detail="Reservation creation failed") from exc
    db.refresh(reservation)
    return ReservationOut.model_validate(reservation, from_attributes=True)


@router.delete("/{reservation_id}", status_code=204)
def cancel_reservation(
    reservation_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> None:
    reservation = db.get(Reservation, reservation_id)
    # Someone else's booking is reported as missing, so ids cannot be probed.
    if reservation is None or reservation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Booking not found")
    # Once charging has started (or finished) the booking is a record of what
    # happened, not something to cancel.
    if ensure_utc(reservation.start_time) <= datetime.now(UTC):
        raise HTTPException(status_code=409, detail="This booking has already started")
    db.delete(reservation)
    db.commit()


@router.get("/mine", response_model=list[ReservationDetailOut])
def my_reservations(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> list[ReservationDetailOut]:
    rows = db.execute(
        select(
            Reservation.id,
            Reservation.charger_id,
            Reservation.user_id,
            Reservation.start_time,
            Reservation.end_time,
            Charger.name.label("charger_name"),
            Station.name.label("station_name"),
        )
        .join(Charger, Charger.id == Reservation.charger_id)
        .join(Station, Station.id == Charger.station_id)
        .where(Reservation.user_id == user_id)
        .order_by(Reservation.start_time.desc())
    )
    return [ReservationDetailOut.model_validate(row, from_attributes=True) for row in rows]
