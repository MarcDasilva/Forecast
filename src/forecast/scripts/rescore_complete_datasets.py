from __future__ import annotations

import asyncio

from sqlalchemy import select

from forecast.db.models import Dataset
from forecast.db.session import get_session_factory
from forecast.scoring.service import ScoringService


async def main_async() -> None:
    session_factory = get_session_factory()
    scoring_service = ScoringService()

    async with session_factory() as session:
        dataset_ids = list(
            await session.scalars(select(Dataset.id).where(Dataset.status == "complete"))
        )

    for dataset_id in dataset_ids:
        async with session_factory() as session:
            async with session.begin():
                await scoring_service.score_dataset(session, dataset_id)
        print(dataset_id)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
