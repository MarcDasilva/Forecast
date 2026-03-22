from __future__ import annotations

import asyncio

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client, tracing_context
from langsmith import utils as langsmith_utils

from forecast.agents.summariser import SummariserService
from forecast.config import get_settings


RAW_DATA = """
City of Toronto Housing Survey 2025
Geography: Toronto
Period: 2025
Vacancy rate: 4.2
Housing cost burden percentage: 38.1
New housing starts per 1,000 residents: 7.4
Notes: Survey combines municipal reporting with annual housing market data.
""".strip()


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
            result = asyncio.run(SummariserService().summarise_text(RAW_DATA))
        print(result.model_dump_json(indent=2))
    finally:
        wait_for_all_tracers()


if __name__ == "__main__":
    main()
