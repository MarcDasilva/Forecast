from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forecast.config import Settings, get_settings
from forecast.db.models import AnchorEmbedding, Dataset, DatasetEmbedding
from forecast.embeddings.schemas import EmbeddingResult


class DatasetRepository:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def validate_embedding_dimensions(self, embedding: list[float]) -> None:
        expected_dimensions = self.settings.openai_embed_dimensions
        actual_dimensions = len(embedding)
        if actual_dimensions != expected_dimensions:
            raise ValueError(
                f"Embedding dimensions mismatch: expected {expected_dimensions}, "
                f"received {actual_dimensions}."
            )

    async def create_dataset(
        self,
        session: AsyncSession,
        *,
        input_type: str,
        source_ref: str,
        raw_text: str | None = None,
        summary: dict[str, object] | None = None,
        status: str = "pending",
    ) -> Dataset:
        dataset = Dataset(
            input_type=input_type,
            source_ref=source_ref,
            raw_text=raw_text,
            summary=summary,
            status=status,
        )
        session.add(dataset)
        await session.flush()
        return dataset

    async def get_dataset(self, session: AsyncSession, dataset_id: uuid.UUID) -> Dataset | None:
        return await session.get(Dataset, dataset_id)

    async def upsert_dataset_embedding(
        self,
        session: AsyncSession,
        *,
        dataset_id: uuid.UUID,
        embedding_result: EmbeddingResult,
    ) -> DatasetEmbedding:
        self.validate_embedding_dimensions(embedding_result.embedding)

        existing = await session.scalar(
            select(DatasetEmbedding).where(DatasetEmbedding.dataset_id == dataset_id)
        )

        if existing is None:
            existing = DatasetEmbedding(
                dataset_id=dataset_id,
                embed_input=embedding_result.embed_input,
                embedding=embedding_result.embedding,
                model=embedding_result.model,
            )
            session.add(existing)
        else:
            existing.embed_input = embedding_result.embed_input
            existing.embedding = embedding_result.embedding
            existing.model = embedding_result.model

        await session.flush()
        return existing


class AnchorRepository:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def validate_embedding_dimensions(self, embedding: list[float]) -> None:
        expected_dimensions = self.settings.openai_embed_dimensions
        actual_dimensions = len(embedding)
        if actual_dimensions != expected_dimensions:
            raise ValueError(
                f"Embedding dimensions mismatch: expected {expected_dimensions}, "
                f"received {actual_dimensions}."
            )

    async def upsert_anchor_embedding(
        self,
        session: AsyncSession,
        *,
        category: str,
        anchor_text: str,
        embedding: list[float],
    ) -> AnchorEmbedding:
        self.validate_embedding_dimensions(embedding)

        existing = await session.get(AnchorEmbedding, category)
        if existing is None:
            existing = AnchorEmbedding(
                category=category,
                anchor_text=anchor_text,
                embedding=embedding,
            )
            session.add(existing)
        else:
            existing.anchor_text = anchor_text
            existing.embedding = embedding

        await session.flush()
        return existing

    async def list_anchor_embeddings(self, session: AsyncSession) -> list[AnchorEmbedding]:
        result = await session.scalars(
            select(AnchorEmbedding).order_by(AnchorEmbedding.category.asc())
        )
        return list(result)
