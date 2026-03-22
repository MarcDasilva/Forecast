from __future__ import annotations

from typing import Any

import pytest

from forecast.agents.classifier import ClassificationResult
from forecast.agents.graph import PipelineGraphService
from forecast.embeddings.schemas import SummarySchema


class FakeClassifierService:
    async def classify_and_prepare(self, raw_input: str) -> ClassificationResult:
        return ClassificationResult(input_type="csv", normalized_text=f"normalized::{raw_input}")


class FakeSummariserService:
    async def summarise_text(self, raw_text: str) -> SummarySchema:
        return SummarySchema(
            title="Synthetic Dataset",
            domain="healthcare",
            geography="Toronto",
            time_period="2025-Q4",
            key_metrics={"hospital_beds_per_1000": 2.92},
            civic_relevance="Useful for healthcare planning.",
            data_quality_notes="Synthetic test data.",
        )


class FakeEmbeddingService:
    async def embed_summary(self, summary: dict[str, object]) -> Any:
        class Result:
            embed_input = "embed me"
            embedding = [0.1, 0.2, 0.3, 0.4]
            model = "test-embed-model"

        return Result()


class FakeDatasetRepository:
    def __init__(self) -> None:
        self.updated: list[dict[str, object]] = []
        self.embeddings: list[dict[str, object]] = []

    async def update_dataset(self, session: object, **kwargs: object) -> object:
        self.updated.append(kwargs)
        return object()

    async def upsert_dataset_embedding(self, session: object, **kwargs: object) -> object:
        self.embeddings.append(kwargs)
        return object()


class FakeSessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeSession:
    def begin(self) -> FakeSessionContext:
        return FakeSessionContext()

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeSessionFactory:
    def __call__(self) -> FakeSession:
        return FakeSession()


@pytest.mark.asyncio
async def test_pipeline_graph_runs_all_nodes_and_persists() -> None:
    repository = FakeDatasetRepository()
    service = PipelineGraphService(
        classifier_service=FakeClassifierService(),
        summariser_service=FakeSummariserService(),
        embedding_service=FakeEmbeddingService(),
        dataset_repository=repository,
        session_factory=FakeSessionFactory(),
    )

    result = await service.run(
        {
            "dataset_id": "9d9a6cb5-56f0-4f45-a282-4f1fc89f17d5",
            "source_ref": "sample.csv",
            "raw_input": "city,beds\nToronto,2.8",
            "status": "pending",
            "error": None,
        }
    )

    assert result["status"] == "complete"
    assert result["input_type"] == "csv"
    assert result["summary"]["domain"] == "healthcare"
    assert result["embedding_model"] == "test-embed-model"
    assert len(repository.updated) == 1
    assert len(repository.embeddings) == 1
