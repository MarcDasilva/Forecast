from __future__ import annotations

from typing import Any

from sqlalchemy import text

from forecast.config import Settings, get_settings
from forecast.db.session import get_session_factory
from forecast.embeddings.service import EmbeddingService
from forecast.scoring.benchmarks import IMPORTANCE_WEIGHTS
from forecast.scoring.service import ScoringService


class AgentDataService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedding_service = embedding_service or EmbeddingService(settings=self.settings)

    async def get_category_scores(self) -> dict[str, float]:
        session_factory = get_session_factory()
        scoring_service = ScoringService()
        async with session_factory() as session:
            scores, _, _ = await scoring_service.get_aggregated_scores(session)
        return {category: scores.get(category, 0.0) for category in IMPORTANCE_WEIGHTS}

    async def get_dataset_summaries(self, category: str, limit: int = 5) -> list[dict[str, Any]]:
        session_factory = get_session_factory()
        async with session_factory() as session:
            rows = list(
                await session.execute(
                    text(
                        """
                        SELECT
                            d.id,
                            d.source_ref,
                            d.summary,
                            cs.category,
                            cs.cosine_similarity,
                            cs.benchmark_eval,
                            cs.final_score,
                            d.created_at
                        FROM category_scores cs
                        JOIN datasets d ON d.id = cs.dataset_id
                        WHERE d.status = 'complete'
                          AND d.summary IS NOT NULL
                          AND cs.category = :category
                        ORDER BY cs.cosine_similarity DESC, d.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"category": category, "limit": limit},
                )
            )

        return [
            {
                "id": str(row.id),
                "source_ref": row.source_ref,
                "category": row.category,
                "similarity": float(row.cosine_similarity),
                "benchmark_eval": float(row.benchmark_eval),
                "final_score": float(row.final_score),
                "summary": row.summary,
            }
            for row in rows
        ]

    async def search_datasets(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_embedding = await self.embedding_service.embed_text(query)
        vector_literal = "[" + ",".join(f"{value:.8f}" for value in query_embedding) + "]"
        session_factory = get_session_factory()
        async with session_factory() as session:
            rows = list(
                await session.execute(
                    text(
                        """
                        SELECT
                            d.id,
                            d.source_ref,
                            d.summary,
                            1 - (de.embedding <=> CAST(:query_embedding AS vector)) AS similarity
                        FROM dataset_embeddings de
                        JOIN datasets d ON d.id = de.dataset_id
                        WHERE d.status = 'complete'
                          AND d.summary IS NOT NULL
                        ORDER BY de.embedding <=> CAST(:query_embedding AS vector)
                        LIMIT :limit
                        """
                    ),
                    {"query_embedding": vector_literal, "limit": limit},
                )
            )

        return [
            {
                "id": str(row.id),
                "source_ref": row.source_ref,
                "similarity": float(row.similarity),
                "summary": row.summary,
            }
            for row in rows
        ]
