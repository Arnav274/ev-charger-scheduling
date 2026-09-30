from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dijkstra import RoadGraphUnavailable
from app.recommendation import recommend
from app.schemas import RecommendationOut, RecommendationRequest

router = APIRouter(tags=["recommendations"])


@router.post("/recommendations", response_model=list[RecommendationOut])
def recommendations(payload: RecommendationRequest, db: Session = Depends(get_db)) -> list[RecommendationOut]:
    try:
        return recommend(db, payload, now=datetime.now(UTC))
    except RoadGraphUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
