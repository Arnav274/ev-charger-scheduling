from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.recommendation import recommend
from app.schemas import RecommendationOut, RecommendationRequest

router = APIRouter(tags=["recommendations"])


@router.post("/recommendations", response_model=list[RecommendationOut])
def recommendations(payload: RecommendationRequest, db: Session = Depends(get_db)) -> list[RecommendationOut]:
    return recommend(db, payload, now=datetime.now(UTC))
