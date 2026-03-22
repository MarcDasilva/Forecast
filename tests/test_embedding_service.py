from __future__ import annotations

from langchain_core.embeddings import Embeddings

from forecast.config import Settings
from forecast.embeddings.schemas import SummarySchema
from forecast.embeddings.service import EmbeddingService, build_embed_input


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


def test_build_embed_input_skips_null_metrics() -> None:
    summary = SummarySchema(
        title="Transit Access Snapshot",
        domain="transportation",
        geography="Waterloo",
        time_period="2025",
        key_metrics={
            "transit_modal_share": 42.0,
            "average_commute_time": 31.5,
            "cycling_modal_share": None,
        },
        civic_relevance="Shows how residents access jobs and services.",
        data_quality_notes="Compiled from annual survey responses.",
    )

    embed_input = build_embed_input(summary)

    assert "Transit Access Snapshot." in embed_input
    assert "Shows how residents access jobs and services." in embed_input
    assert "transit_modal_share: 42" in embed_input
    assert "average_commute_time: 31.5" in embed_input
    assert "cycling_modal_share" not in embed_input


async def test_embedding_service_embeds_summary_with_injected_client() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_embed_model="text-embedding-3-small",
        langsmith_tracing=False,
    )
    service = EmbeddingService(settings=settings, embeddings_client=FakeEmbeddings())

    result = await service.embed_summary(
        {
            "title": "Housing Affordability Monitor",
            "domain": "housing",
            "geography": "Toronto",
            "time_period": "2025",
            "key_metrics": {"cost_burden_pct": 38.1, "vacancy_rate": 4.2},
            "civic_relevance": "Tracks whether housing remains affordable for residents.",
            "data_quality_notes": "Derived from municipal reporting.",
        }
    )

    assert result.model == "text-embedding-3-small"
    assert result.embed_input.startswith("Housing Affordability Monitor.")
    assert result.embedding == [float(len(result.embed_input))]
