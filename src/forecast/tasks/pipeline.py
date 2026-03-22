from __future__ import annotations

import uuid

from celery import Celery

from forecast.agents.graph import PipelineGraphService
from forecast.config import get_settings
from forecast.db.repositories import DatasetRepository
from forecast.db.session import get_session_factory

settings = get_settings()

celery_app = Celery(
    "forecast",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_store_eager_result=False,
)


@celery_app.task(name="forecast.process_dataset")
def process_dataset_task(dataset_id: str) -> None:
    import asyncio

    asyncio.run(process_dataset(dataset_id))


async def process_dataset(dataset_id: str) -> None:
    session_factory = get_session_factory()
    repository = DatasetRepository()
    graph_service = PipelineGraphService(
        dataset_repository=repository,
        session_factory=session_factory,
    )

    dataset_uuid = uuid.UUID(dataset_id)

    async with session_factory() as session:
        dataset = await repository.get_dataset(session, dataset_uuid)
        if dataset is None:
            raise ValueError(f"Dataset {dataset_id} not found.")

    async with session_factory() as session:
        async with session.begin():
            await repository.update_dataset(
                session,
                dataset_id=dataset_uuid,
                status="processing",
                error_msg=None,
            )

    try:
        await graph_service.run(
            {
                "dataset_id": dataset_id,
                "source_ref": dataset.source_ref,
                "raw_input": dataset.raw_text or dataset.source_ref,
                "status": "processing",
                "error": None,
            }
        )
    except Exception as error:
        async with session_factory() as session:
            async with session.begin():
                await repository.update_dataset(
                    session,
                    dataset_id=dataset_uuid,
                    status="error",
                    error_msg=str(error),
                )
        raise


async def enqueue_dataset_processing(dataset_id: str) -> None:
    if settings.celery_task_always_eager:
        await process_dataset(dataset_id)
    else:
        process_dataset_task.delay(dataset_id)


from forecast.tasks import specialists as _specialists  # noqa: E402,F401
