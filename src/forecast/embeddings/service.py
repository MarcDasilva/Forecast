from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from forecast.config import Settings, get_settings
from forecast.embeddings.schemas import EmbeddingResult, SummarySchema


def _format_metric_value(value: float) -> str:
    return f"{value:g}"


def build_embed_input(summary: SummarySchema) -> str:
    metrics = [
        f"{name}: {_format_metric_value(value)}"
        for name, value in summary.key_metrics.items()
        if value is not None
    ]

    parts = [f"{summary.title}.", summary.civic_relevance.strip()]
    if metrics:
        parts.append(f"Key metrics: {', '.join(metrics)}.")

    return " ".join(part for part in parts if part).strip()


class EmbeddingService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        embeddings_client: Embeddings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.configure_langsmith()
        self.embeddings_client = embeddings_client or OpenAIEmbeddings(
            model=self.settings.openai_embed_model,
            dimensions=self.settings.openai_embed_dimensions,
            api_key=self.settings.openai_api_key_value(),
        )

    async def embed_text(self, text: str) -> list[float]:
        return [float(value) for value in await self.embeddings_client.aembed_query(text)]

    async def embed_summary(self, summary: SummarySchema | dict[str, object]) -> EmbeddingResult:
        parsed_summary = summary if isinstance(summary, SummarySchema) else SummarySchema.model_validate(summary)
        embed_input = build_embed_input(parsed_summary)
        embedding = await self.embed_text(embed_input)
        return EmbeddingResult(
            embed_input=embed_input,
            embedding=embedding,
            model=self.settings.openai_embed_model,
        )
