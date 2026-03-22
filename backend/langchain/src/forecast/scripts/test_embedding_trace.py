from __future__ import annotations

import asyncio

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client, traceable, tracing_context
from langsmith import utils as langsmith_utils

from forecast.config import get_settings
from forecast.embeddings.service import EmbeddingService


SUMMARY = {
    "title": "Housing Affordability Monitor",
    "domain": "housing",
    "geography": "Toronto",
    "time_period": "2025",
    "key_metrics": {
        "cost_burden_pct": 38.1,
        "vacancy_rate": 4.2,
    },
    "civic_relevance": "Tracks whether housing remains affordable for residents.",
    "data_quality_notes": "Derived from municipal reporting.",
}


@traceable(name="manual_embedding_test", run_type="chain")
async def run_embedding_test() -> dict[str, object]:
    service = EmbeddingService()
    result = await service.embed_summary(SUMMARY)
    return {
        "model": result.model,
        "dimensions": len(result.embedding),
        "embed_input": result.embed_input,
    }


def main() -> None:
    settings = get_settings()
    settings.configure_langsmith()
    langsmith_utils.get_env_var.cache_clear()
    if not settings.langsmith_api_key:
        raise ValueError("LANGSMITH_API_KEY is required to send traces to LangSmith.")

    client = Client(
        api_key=settings.langsmith_api_key.get_secret_value(),
        api_url=settings.langsmith_endpoint,
        workspace_id=settings.langsmith_workspace_id,
    )

    try:
        with tracing_context(
            enabled=True,
            client=client,
            project_name=settings.langsmith_project,
        ):
            result = asyncio.run(run_embedding_test())
        print(result["model"])
        print(result["dimensions"])
        print(result["embed_input"])
    finally:
        wait_for_all_tracers()


if __name__ == "__main__":
    main()
