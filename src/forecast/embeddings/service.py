from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from forecast.config import Settings, get_settings
from forecast.embeddings.schemas import EmbeddingResult, SummarySchema


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def build_embed_input(summary: SummarySchema) -> str:
    metric_names = [name for name, value in summary.key_metrics.items() if value is not None]
    parts = [
        f"domain:{summary.domain}",
        f"title:{summary.title.strip()}",
    ]

    geography = _clean_text(summary.geography)
    if geography and geography != "unknown":
        parts.append(f"geography:{geography}")

    time_period = _clean_text(summary.time_period)
    if time_period and time_period != "unknown":
        parts.append(f"time_period:{time_period}")

    if metric_names:
        parts.append(f"metrics:{', '.join(metric_names)}")

    return " | ".join(parts)


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
