from __future__ import annotations

from fastapi import APIRouter

from forecast.db.session import get_session_factory
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
