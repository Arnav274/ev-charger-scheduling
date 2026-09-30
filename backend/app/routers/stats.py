import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter

from app.schemas import ExperimentSummaryResponse

router = APIRouter(prefix="/stats", tags=["stats"])

EXPERIMENT_OUTPUTS = Path(__file__).resolve().parents[2] / "experiments" / "outputs"


@router.get("/experiment-summary", response_model=ExperimentSummaryResponse)
def experiment_summary() -> ExperimentSummaryResponse:
    path = EXPERIMENT_OUTPUTS / "summary_ci.csv"
    if not path.is_file():
        return ExperimentSummaryResponse(rows=[])
    # Round-trip through JSON so NaN becomes null rather than an invalid float.
    return ExperimentSummaryResponse(rows=json.loads(pd.read_csv(path).to_json(orient="records")))
