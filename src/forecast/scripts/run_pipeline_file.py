from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client, tracing_context
from langsmith import utils as langsmith_utils

from forecast.agents.graph import PipelineGraphService
from forecast.config import get_settings
from forecast.db.repositories import DatasetRepository
from forecast.db.session import get_session_factory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ingestion pipeline on a local file.")
    parser.add_argument("path", help="Path to the file to ingest.")
    return parser.parse_args()


async def run_pipeline(path: str) -> dict[str, object]:
    file_path = Path(path)
    raw_input = file_path.read_text(encoding="utf-8")

    session_factory = get_session_factory()
    repository = DatasetRepository()

    async with session_factory() as session:
        async with session.begin():
            dataset = await repository.create_dataset(
                session,
                input_type="text",
                source_ref=str(file_path),
                raw_text=raw_input,
                status="pending",
            )
        dataset_id = str(dataset.id)

    graph_service = PipelineGraphService(
        dataset_repository=repository,
        session_factory=session_factory,
    )

    try:
        result = await graph_service.run(
            {
                "dataset_id": dataset_id,
                "source_ref": str(file_path),
                "raw_input": raw_input,
                "status": "pending",
                "error": None,
            }
        )
        return {
            "dataset_id": dataset_id,
            "status": result["status"],
            "input_type": result["input_type"],
            "summary": result["summary"],
            "embedding_dimensions": len(result["embedding"]),
        }
    except Exception as error:
        async with session_factory() as session:
            async with session.begin():
                await repository.update_dataset(
                    session,
                    dataset_id=dataset.id,
                    status="error",
                    error_msg=str(error),
                )
        raise


def main() -> None:
    args = parse_args()
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
            result = asyncio.run(run_pipeline(args.path))
        print(result)
    finally:
        wait_for_all_tracers()


if __name__ == "__main__":
    main()
