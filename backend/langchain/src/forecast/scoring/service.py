from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, literal, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from forecast.db.models import AnchorEmbedding, CategoryScore, Dataset, DatasetEmbedding
from forecast.scoring.benchmarks import (
    BENCHMARK_EVALUATORS,
    IMPORTANCE_WEIGHTS,
    clamp,
    explain_benchmark,
)


@dataclass
class CategoryScoreResult:
    category: str
    cosine_similarity: float
    benchmark_eval: float
    importance_weight: float
    final_score: float


def compute_final_score(
    *,
    benchmark_eval: float,
    cosine_similarity: float,
    importance_weight: float,
) -> float:
    return benchmark_eval * cosine_similarity * 100


def aggregate_category_score(scores: list[CategoryScore]) -> float:
    total_weight = sum(score.cosine_similarity for score in scores)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(score.final_score * score.cosine_similarity for score in scores)
    return weighted_sum / total_weight


class ScoringService:
    async def score_dataset(self, session: AsyncSession, dataset_id: uuid.UUID) -> list[CategoryScoreResult]:
        dataset = await session.get(Dataset, dataset_id)
        if dataset is None or dataset.summary is None:
            raise ValueError(f"Dataset {dataset_id} is missing summary data.")

        embedding_row = await session.scalar(
            select(DatasetEmbedding).where(DatasetEmbedding.dataset_id == dataset_id)
        )
        if embedding_row is None:
            raise ValueError(f"Dataset {dataset_id} is missing an embedding.")

        similarities = await self._get_anchor_similarities(session, dataset_id)
        metrics = dataset.summary.get("key_metrics", {})

        results: list[CategoryScoreResult] = []
        for category, similarity in similarities.items():
            evaluator = BENCHMARK_EVALUATORS[category]
            benchmark_eval = evaluator(metrics)
            importance_weight = IMPORTANCE_WEIGHTS[category]
            final_score = compute_final_score(
                benchmark_eval=benchmark_eval,
                cosine_similarity=similarity,
                importance_weight=importance_weight,
            )
            results.append(
                CategoryScoreResult(
                    category=category,
                    cosine_similarity=similarity,
                    benchmark_eval=benchmark_eval,
                    importance_weight=importance_weight,
                    final_score=final_score,
                )
            )

        for result in results:
            await self._upsert_category_score(session, dataset_id, result)

        return results

    async def _get_anchor_similarities(
        self,
        session: AsyncSession,
        dataset_id: uuid.UUID,
    ) -> dict[str, float]:
        result = await session.execute(
            select(
                AnchorEmbedding.category,
                (literal(1.0) - DatasetEmbedding.embedding.cosine_distance(AnchorEmbedding.embedding)).label(
                    "similarity"
                ),
            )
            .select_from(DatasetEmbedding)
            .join(AnchorEmbedding, true())
            .where(DatasetEmbedding.dataset_id == dataset_id)
        )
        return {row.category: clamp(float(row.similarity)) for row in result}

    async def _upsert_category_score(
        self,
        session: AsyncSession,
        dataset_id: uuid.UUID,
        result: CategoryScoreResult,
    ) -> CategoryScore:
        existing = await session.scalar(
            select(CategoryScore).where(
                CategoryScore.dataset_id == dataset_id,
                CategoryScore.category == result.category,
            )
        )
        if existing is None:
            existing = CategoryScore(
                dataset_id=dataset_id,
                category=result.category,
                cosine_similarity=result.cosine_similarity,
                benchmark_eval=result.benchmark_eval,
                importance_weight=result.importance_weight,
                final_score=result.final_score,
            )
            session.add(existing)
        else:
            existing.cosine_similarity = result.cosine_similarity
            existing.benchmark_eval = result.benchmark_eval
            existing.importance_weight = result.importance_weight
            existing.final_score = result.final_score
        await session.flush()
        return existing

    async def get_aggregated_scores(
        self,
        session: AsyncSession,
    ) -> tuple[dict[str, float], int, datetime | None]:
        score_rows = list(
            await session.scalars(
                select(CategoryScore).order_by(CategoryScore.category.asc(), CategoryScore.created_at.desc())
            )
        )
        grouped: dict[str, list[CategoryScore]] = {category: [] for category in IMPORTANCE_WEIGHTS}
        for row in score_rows:
            grouped.setdefault(row.category, []).append(row)

        aggregated = {
            category: round(aggregate_category_score(grouped.get(category, [])), 2)
            for category in IMPORTANCE_WEIGHTS
        }

        dataset_count = await session.scalar(
            select(func.count(Dataset.id)).where(Dataset.status == "complete")
        )
        last_updated = await session.scalar(select(func.max(CategoryScore.created_at)))
        return aggregated, int(dataset_count or 0), last_updated

    async def explain_category_score(
        self,
        session: AsyncSession,
        *,
        category: str,
        limit: int = 3,
    ) -> dict[str, Any]:
        score_rows = list(
            await session.execute(
                select(Dataset, CategoryScore)
                .join(CategoryScore, CategoryScore.dataset_id == Dataset.id)
                .where(
                    Dataset.status == "complete",
                    Dataset.summary.is_not(None),
                    CategoryScore.category == category,
                )
                .order_by(CategoryScore.final_score.desc(), Dataset.created_at.desc())
            )
        )
        aggregated_scores, _, _ = await self.get_aggregated_scores(session)
        total_similarity = sum(score.cosine_similarity for _, score in score_rows)

        top_contributors: list[dict[str, Any]] = []
        for dataset, score in score_rows[:limit]:
            metrics = (dataset.summary or {}).get("key_metrics", {})
            benchmark_breakdown = explain_benchmark(category, metrics)
            top_contributors.append(
                {
                    "dataset_id": str(dataset.id),
                    "source_ref": dataset.source_ref,
                    "title": (dataset.summary or {}).get("title"),
                    "geography": (dataset.summary or {}).get("geography"),
                    "time_period": (dataset.summary or {}).get("time_period"),
                    "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
                    "final_score": float(score.final_score),
                    "similarity": float(score.cosine_similarity),
                    "benchmark_eval": float(score.benchmark_eval),
                    "contribution_weight": (
                        float(score.cosine_similarity / total_similarity) if total_similarity else 0.0
                    ),
                    "score_equation": (
                        f"{score.benchmark_eval:.3f} x {score.cosine_similarity:.3f} x 100 = "
                        f"{score.final_score:.2f}"
                    ),
                    "benchmark_breakdown": benchmark_breakdown,
                }
            )

        return {
            "category": category,
            "aggregated_score": float(aggregated_scores.get(category, 0.0)),
            "dataset_count": len(score_rows),
            "importance_weight": float(IMPORTANCE_WEIGHTS[category]),
            "importance_weight_used_in_final_score": False,
            "scoring_formula": "dataset_final_score = benchmark_eval * cosine_similarity * 100",
            "aggregation_formula": (
                "category_score = similarity-weighted average of dataset final scores"
            ),
            "benchmark_formula": "benchmark_eval = average(normalized metric component scores)",
            "top_contributors": top_contributors,
        }
