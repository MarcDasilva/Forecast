from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from forecast.db.models import CategoryScore, Dataset
from forecast.db.repositories import DatasetRepository
from forecast.db.session import get_session_factory
from forecast.scoring.benchmarks import IMPORTANCE_WEIGHTS

router = APIRouter(prefix="/datasets", tags=["datasets"])


class DatasetRenameRequest(BaseModel):
    summary_title: str = Field(min_length=1, max_length=2000)


async def _serialize_dataset(session, dataset: Dataset) -> dict[str, object]:
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


@router.get("/relevant/{category}")
async def get_relevant_datasets(
    category: str,
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, object]:
    if category not in IMPORTANCE_WEIGHTS:
        raise HTTPException(status_code=400, detail=f"Unsupported category '{category}'.")

    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = list(
            await session.execute(
                select(Dataset, CategoryScore)
                .join(CategoryScore, CategoryScore.dataset_id == Dataset.id)
                .where(
                    Dataset.status == "complete",
                    Dataset.summary.is_not(None),
                    CategoryScore.category == category,
                )
                .order_by(CategoryScore.final_score.desc(), Dataset.created_at.desc())
                .limit(limit)
            )
        )

    return {
        "category": category,
        "items": [
            {
                "id": str(dataset.id),
                "source_ref": dataset.source_ref,
                "input_type": dataset.input_type,
                "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
                "title": (dataset.summary or {}).get("title"),
                "geography": (dataset.summary or {}).get("geography"),
                "time_period": (dataset.summary or {}).get("time_period"),
                "final_score": score.final_score,
                "benchmark_eval": score.benchmark_eval,
                "similarity": score.cosine_similarity,
            }
            for dataset, score in rows
        ],
    }


@router.get("/{dataset_id}/metric-history")
async def get_dataset_metric_history(dataset_id: str) -> dict[str, object]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        dataset = await session.get(Dataset, uuid.UUID(dataset_id))
        if dataset is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")

        history_rows = list(
            await session.scalars(
                select(Dataset)
                .where(
                    Dataset.source_ref == dataset.source_ref,
                    Dataset.status == "complete",
                    Dataset.summary.is_not(None),
                )
                .order_by(Dataset.created_at.asc())
            )
        )

    series: dict[str, list[dict[str, object]]] = {}
    for row in history_rows:
        metrics = (row.summary or {}).get("key_metrics", {})
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, bool) or not isinstance(metric_value, (int, float)):
                continue
            series.setdefault(metric_name, []).append(
                {
                    "dataset_id": str(row.id),
                    "observed_at": row.created_at.isoformat() if row.created_at else None,
                    "value": float(metric_value),
                }
            )

    return {
        "dataset_id": str(dataset.id),
        "source_ref": dataset.source_ref,
        "title": (dataset.summary or {}).get("title"),
        "series": series,
        "run_count": len(history_rows),
    }


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str) -> dict[str, object]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        dataset = await session.get(Dataset, uuid.UUID(dataset_id))
        if dataset is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")

        return await _serialize_dataset(session, dataset)


@router.patch("/{dataset_id}")
async def rename_dataset(dataset_id: str, payload: DatasetRenameRequest) -> dict[str, object]:
    summary_title = payload.summary_title.strip()
    if not summary_title:
        raise HTTPException(status_code=400, detail="Summary title cannot be empty.")

    session_factory = get_session_factory()
    repository = DatasetRepository()
    async with session_factory() as session:
        dataset = await session.get(Dataset, uuid.UUID(dataset_id))
        if dataset is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")

        next_summary = dict(dataset.summary or {})
        next_summary["title"] = summary_title
        await repository.update_dataset(
            session,
            dataset_id=dataset.id,
            summary=next_summary,
            error_msg=dataset.error_msg,
        )
        return await _serialize_dataset(session, dataset)
