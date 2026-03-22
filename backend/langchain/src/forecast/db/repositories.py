from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forecast.config import Settings, get_settings
from forecast.agents.context_loader import SPECIALIST_CATEGORIES
from forecast.db.models import (
    AnchorEmbedding,
    Dataset,
    DatasetArtifact,
    DatasetEmbedding,
    SourceRecording,
    SpecialistAgentScore,
)
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

    async def create_dataset_artifact(
        self,
        session: AsyncSession,
        *,
        dataset_id: uuid.UUID,
        artifact_type: str,
        label: str,
        filename: str,
        mime_type: str,
        storage_path: str,
        size_bytes: int,
        artifact_meta: dict[str, object] | None = None,
    ) -> DatasetArtifact:
        artifact = DatasetArtifact(
            dataset_id=dataset_id,
            artifact_type=artifact_type,
            label=label,
            filename=filename,
            mime_type=mime_type,
            storage_path=storage_path,
            size_bytes=size_bytes,
            artifact_meta=artifact_meta or {},
        )
        session.add(artifact)
        await session.flush()
        return artifact

    async def list_dataset_artifacts(
        self,
        session: AsyncSession,
        *,
        dataset_id: uuid.UUID,
    ) -> list[DatasetArtifact]:
        result = await session.scalars(
            select(DatasetArtifact)
            .where(DatasetArtifact.dataset_id == dataset_id)
            .order_by(DatasetArtifact.created_at.desc())
        )
        return list(result)

    async def get_dataset_artifact(
        self,
        session: AsyncSession,
        artifact_id: uuid.UUID,
    ) -> DatasetArtifact | None:
        return await session.get(DatasetArtifact, artifact_id)

    async def create_source_recording(
        self,
        session: AsyncSession,
        *,
        source_ref: str,
        source_url: str | None,
        title: str | None,
        artifact_type: str,
        label: str,
        filename: str,
        mime_type: str,
        storage_path: str,
        size_bytes: int,
        recording_meta: dict[str, object] | None = None,
    ) -> SourceRecording:
        recording = SourceRecording(
            source_ref=source_ref,
            source_url=source_url,
            title=title,
            artifact_type=artifact_type,
            label=label,
            filename=filename,
            mime_type=mime_type,
            storage_path=storage_path,
            size_bytes=size_bytes,
            recording_meta=recording_meta or {},
        )
        session.add(recording)
        await session.flush()
        return recording

    async def get_source_recording(
        self,
        session: AsyncSession,
        recording_id: uuid.UUID,
    ) -> SourceRecording | None:
        return await session.get(SourceRecording, recording_id)

    async def update_dataset(
        self,
        session: AsyncSession,
        *,
        dataset_id: uuid.UUID,
        source_ref: str | None = None,
        input_type: str | None = None,
        raw_text: str | None = None,
        summary: dict[str, object] | None = None,
        status: str | None = None,
        error_msg: str | None = None,
    ) -> Dataset:
        dataset = await self.get_dataset(session, dataset_id)
        if dataset is None:
            raise ValueError(f"Dataset {dataset_id} not found.")

        if source_ref is not None:
            dataset.source_ref = source_ref
        if input_type is not None:
            dataset.input_type = input_type
        if raw_text is not None:
            dataset.raw_text = raw_text
        if summary is not None:
            dataset.summary = summary
        if status is not None:
            dataset.status = status
        dataset.error_msg = error_msg

        await session.flush()
        return dataset

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


class SpecialistAssessmentRepository:
    async def create_assessment(
        self,
        session: AsyncSession,
        *,
        category: str,
        agent_name: str,
        score: float,
        status_label: str,
        confidence: float,
        rationale: str,
        benchmark_highlights: list[str],
        recommendations: list[str],
        supporting_evidence: list[str],
        source_dataset_ids: list[str],
    ) -> SpecialistAgentScore:
        assessment = SpecialistAgentScore(
            category=category,
            agent_name=agent_name,
            score=score,
            status_label=status_label,
            confidence=confidence,
            rationale=rationale,
            benchmark_highlights=benchmark_highlights,
            recommendations=recommendations,
            supporting_evidence=supporting_evidence,
            source_dataset_ids=source_dataset_ids,
        )
        session.add(assessment)
        await session.flush()
        return assessment

    async def list_assessments(
        self,
        session: AsyncSession,
        *,
        category: str | None = None,
        limit: int = 20,
    ) -> list[SpecialistAgentScore]:
        query = select(SpecialistAgentScore).order_by(SpecialistAgentScore.created_at.desc())
        if category is not None:
            query = query.where(SpecialistAgentScore.category == category)
        query = query.limit(limit)
        result = await session.scalars(query)
        return list(result)

    async def list_latest_assessments(self, session: AsyncSession) -> list[SpecialistAgentScore]:
        rows = list(
            await session.scalars(
                select(SpecialistAgentScore).order_by(SpecialistAgentScore.created_at.desc())
            )
        )
        latest_by_category: dict[str, SpecialistAgentScore] = {}
        for row in rows:
            latest_by_category.setdefault(row.category, row)
            if len(latest_by_category) == len(SPECIALIST_CATEGORIES):
                break
        return [
            latest_by_category[category]
            for category in SPECIALIST_CATEGORIES
            if category in latest_by_category
        ]
