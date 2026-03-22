from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from forecast.agents.context_loader import SPECIALIST_CATEGORIES, validate_category
from forecast.db.models import SpecialistAgentScore
from forecast.db.repositories import SpecialistAssessmentRepository
from forecast.db.session import get_session_factory

router = APIRouter(prefix="/specialist-scores", tags=["specialist-scores"])


def serialize_assessment(record: SpecialistAgentScore) -> dict[str, object]:
    return {
        "id": str(record.id),
        "category": record.category,
        "agent_name": record.agent_name,
        "score": record.score,
        "status_label": record.status_label,
        "confidence": record.confidence,
        "rationale": record.rationale,
        "benchmark_highlights": record.benchmark_highlights,
        "recommendations": record.recommendations,
        "supporting_evidence": record.supporting_evidence,
        "source_dataset_ids": record.source_dataset_ids,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("")
async def get_specialist_scores() -> dict[str, object]:
    repository = SpecialistAssessmentRepository()
    session_factory = get_session_factory()

    async with session_factory() as session:
        latest_records = await repository.list_latest_assessments(session)

    by_category = {record.category: serialize_assessment(record) for record in latest_records}
    ordered_scores = {category: by_category.get(category) for category in SPECIALIST_CATEGORIES}
    last_updated = max(
        (record.created_at for record in latest_records if record.created_at is not None),
        default=None,
    )

    return {
        "scores": ordered_scores,
        "last_updated": last_updated.isoformat() if last_updated else None,
    }


@router.post("/run/{category}")
async def post_run_specialist_score(category: str) -> dict[str, object]:
    from forecast.tasks.specialists import run_specialist_agent

    try:
        normalized_category = validate_category(category)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    result = await run_specialist_agent(normalized_category)
    return {"result": result}


@router.post("/run-all")
async def post_run_all_specialist_scores() -> dict[str, object]:
    from forecast.tasks.specialists import run_all_specialist_agents

    results = await run_all_specialist_agents()
    return {"results": results}


@router.get("/{category}")
async def get_specialist_score_history(
    category: str,
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, object]:
    try:
        normalized_category = validate_category(category)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    repository = SpecialistAssessmentRepository()
    session_factory = get_session_factory()
    async with session_factory() as session:
        history = await repository.list_assessments(
            session,
            category=normalized_category,
            limit=limit,
        )

    return {
        "category": normalized_category,
        "current": serialize_assessment(history[0]) if history else None,
        "history": [serialize_assessment(record) for record in history],
    }
