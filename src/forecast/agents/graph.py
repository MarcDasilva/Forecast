from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langsmith import traceable
from sqlalchemy.ext.asyncio import AsyncSession

from forecast.agents.classifier import ClassifierService
from forecast.agents.summariser import SummariserService
from forecast.db.repositories import DatasetRepository
from forecast.db.session import get_session_factory
from forecast.embeddings.schemas import EmbeddingResult
from forecast.embeddings.service import EmbeddingService
from forecast.scoring.service import ScoringService


class PipelineState(TypedDict, total=False):
    dataset_id: str
    source_ref: str
    raw_input: str
    input_type: str
    normalized_text: str
    summary: dict[str, Any]
    embed_input: str
    embedding: list[float]
    embedding_model: str
    scores: dict[str, float]
    status: str
    error: str | None


SessionFactory = Callable[[], AsyncIterator[AsyncSession]]


class PipelineGraphService:
    def __init__(
        self,
        *,
        classifier_service: ClassifierService | None = None,
        summariser_service: SummariserService | None = None,
        embedding_service: EmbeddingService | None = None,
        scoring_service: ScoringService | None = None,
        dataset_repository: DatasetRepository | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self.classifier_service = classifier_service or ClassifierService()
        self.summariser_service = summariser_service or SummariserService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.scoring_service = scoring_service or ScoringService()
        self.dataset_repository = dataset_repository or DatasetRepository()
        self.session_factory = session_factory or get_session_factory()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(PipelineState)
        graph.add_node("classifier", self.classifier_node)
        graph.add_node("summariser", self.summariser_node)
        graph.add_node("embedder", self.embedding_node)
        graph.add_node("persist", self.persist_node)
        graph.add_node("scorer", self.scorer_node)
        graph.set_entry_point("classifier")
        graph.add_edge("classifier", "summariser")
        graph.add_edge("summariser", "embedder")
        graph.add_edge("embedder", "persist")
        graph.add_edge("persist", "scorer")
        graph.add_edge("scorer", END)
        return graph.compile()

    @traceable(name="pipeline_classifier_node", run_type="chain")
    async def classifier_node(self, state: PipelineState) -> PipelineState:
        result = await self.classifier_service.classify_and_prepare(state["raw_input"])
        return {
            "input_type": result.input_type,
            "normalized_text": result.normalized_text,
            "status": "processing",
        }

    @traceable(name="pipeline_summariser_node", run_type="chain")
    async def summariser_node(self, state: PipelineState) -> PipelineState:
        summary = await self.summariser_service.summarise_text(state["normalized_text"])
        return {
            "summary": summary.model_dump(),
            "status": "processing",
        }

    @traceable(name="pipeline_embedding_node", run_type="chain")
    async def embedding_node(self, state: PipelineState) -> PipelineState:
        result = await self.embedding_service.embed_summary(state["summary"])
        return {
            "embed_input": result.embed_input,
            "embedding": result.embedding,
            "embedding_model": result.model,
            "status": "processing",
        }

    @traceable(name="pipeline_persist_node", run_type="chain")
    async def persist_node(self, state: PipelineState) -> PipelineState:
        dataset_id = uuid.UUID(state["dataset_id"])
        embedding_result = EmbeddingResult(
            embed_input=state["embed_input"],
            embedding=state["embedding"],
            model=state["embedding_model"],
        )

        async with self.session_factory() as session:
            async with session.begin():
                await self.dataset_repository.update_dataset(
                    session,
                    dataset_id=dataset_id,
                    input_type=state["input_type"],
                    summary=state["summary"],
                    status="complete",
                    error_msg=None,
                )
                await self.dataset_repository.upsert_dataset_embedding(
                    session,
                    dataset_id=dataset_id,
                    embedding_result=embedding_result,
                )

        return {"status": "complete"}

    @traceable(name="pipeline_scorer_node", run_type="chain")
    async def scorer_node(self, state: PipelineState) -> PipelineState:
        dataset_id = uuid.UUID(state["dataset_id"])
        async with self.session_factory() as session:
            async with session.begin():
                results = await self.scoring_service.score_dataset(session, dataset_id)

        return {
            "scores": {result.category: result.final_score for result in results},
            "status": "complete",
        }

    async def run(self, initial_state: PipelineState) -> PipelineState:
        return await self.graph.ainvoke(initial_state)
