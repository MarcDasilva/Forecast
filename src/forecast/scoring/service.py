from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, literal, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from forecast.db.models import AnchorEmbedding, CategoryScore, Dataset, DatasetEmbedding
from forecast.scoring.benchmarks import BENCHMARK_EVALUATORS, IMPORTANCE_WEIGHTS, clamp


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
    return benchmark_eval * cosine_similarity * importance_weight * 100


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
