import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth_deps import get_current_user_id
from app.database import get_db
from app.models import Vehicle
from app.schemas import VehicleCreate, VehicleOut

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("", response_model=VehicleOut, status_code=201)
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


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Session = Depends(get_db),
) -> list[VehicleOut]:
    vehicles = db.query(Vehicle).filter(Vehicle.user_id == user_id).all()
    return [VehicleOut(id=v.id, make_model=v.make_model, battery_kwh=v.battery_kwh) for v in vehicles]
