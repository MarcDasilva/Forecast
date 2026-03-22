from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from forecast.db.repositories import DatasetRepository
from forecast.db.session import get_session_factory
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


async def main() -> None:
    session_factory = get_session_factory()
    repository = DatasetRepository()
    embedding_service = EmbeddingService()

    async with session_factory() as session:
        assert isinstance(session, AsyncSession)
        async with session.begin():
            dataset = await repository.create_dataset(
                session,
                input_type="csv",
                source_ref="manual-test.csv",
                summary=SUMMARY,
                status="complete",
            )
            embedding_result = await embedding_service.embed_summary(SUMMARY)
            stored_embedding = await repository.upsert_dataset_embedding(
                session,
                dataset_id=dataset.id,
                embedding_result=embedding_result,
            )

        print(dataset.id)
        print(stored_embedding.dataset_id)
        print(len(stored_embedding.embedding))
        print(stored_embedding.model)


if __name__ == "__main__":
    asyncio.run(main())
