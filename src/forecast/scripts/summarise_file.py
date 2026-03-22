from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client, tracing_context
from langsmith import utils as langsmith_utils

from forecast.agents.summariser import SummariserService
from forecast.config import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarise a local dataset file.")
    parser.add_argument("path", help="Path to a local file to summarise.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_text = Path(args.path).read_text(encoding="utf-8")

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
            result = asyncio.run(SummariserService().summarise_text(raw_text))
        print(result.model_dump_json(indent=2))
    finally:
        wait_for_all_tracers()


if __name__ == "__main__":
    main()
