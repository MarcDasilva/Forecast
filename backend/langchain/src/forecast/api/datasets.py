from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, func, select

from forecast.db.models import CategoryScore, Dataset
from forecast.db.session import get_session_factory

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
async def get_datasets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
) -> dict[str, object]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        query = select(Dataset).order_by(desc(Dataset.created_at))
        count_query = select(func.count(Dataset.id))
        if status:
            query = query.where(Dataset.status == status)
            count_query = count_query.where(Dataset.status == status)

        query = query.offset((page - 1) * page_size).limit(page_size)
        datasets = list(await session.scalars(query))
        total = await session.scalar(count_query)

    return {
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
        "items": [
            {
                "id": str(dataset.id),
                "source_ref": dataset.source_ref,
                "input_type": dataset.input_type,
                "status": dataset.status,
                "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
            }
            for dataset in datasets
        ],
    }


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str) -> dict[str, object]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        dataset = await session.get(Dataset, uuid.UUID(dataset_id))
        if dataset is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")

        score_rows = list(
            await session.scalars(
                select(CategoryScore)
                .where(CategoryScore.dataset_id == dataset.id)
                .order_by(CategoryScore.category.asc())
            )
        )

    return {
        "id": str(dataset.id),
        "source_ref": dataset.source_ref,
        "status": dataset.status,
        "input_type": dataset.input_type,
        "summary": dataset.summary,
        "error_msg": dataset.error_msg,
        "scores": {
            row.category: {
                "final_score": row.final_score,
                "similarity": row.cosine_similarity,
                "benchmark_eval": row.benchmark_eval,
            }
            for row in score_rows
        },
    }
