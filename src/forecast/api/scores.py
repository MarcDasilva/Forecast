from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from forecast.db.session import get_session_factory
from forecast.forecasting import CategoryForecastService
from forecast.scoring.benchmarks import IMPORTANCE_WEIGHTS
from forecast.scoring.service import ScoringService

router = APIRouter(prefix="/scores", tags=["scores"])


@router.get("")
async def get_scores() -> dict[str, object]:
    session_factory = get_session_factory()
    scoring_service = ScoringService()

    async with session_factory() as session:
        scores, dataset_count, last_updated = await scoring_service.get_aggregated_scores(session)

    return {
        "scores": {category: scores.get(category, 0.0) for category in IMPORTANCE_WEIGHTS},
        "dataset_count": dataset_count,
        "last_updated": last_updated.isoformat() if last_updated else None,
    }


@router.get("/forecast/{category}")
async def get_category_forecast(
    category: str,
    mode: Literal["time_to_target", "required_rate"] = Query(default="time_to_target"),
    target_y: float = Query(..., ge=0.0, le=100.0),
    target_date: date | None = Query(default=None),
    target_days: int | None = Query(default=None, ge=1, le=3650),
    forecast_periods: int = Query(default=365, ge=30, le=3650),
) -> dict[str, object]:
    if category not in IMPORTANCE_WEIGHTS:
        raise HTTPException(status_code=400, detail=f"Unsupported category '{category}'.")

    session_factory = get_session_factory()
    forecasting_service = CategoryForecastService()

    async with session_factory() as session:
        try:
            return await forecasting_service.get_category_forecast(
                session,
                category=category,
                mode=mode,
                target_y=target_y,
                target_date=target_date,
                target_days=target_days,
                forecast_periods=forecast_periods,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
