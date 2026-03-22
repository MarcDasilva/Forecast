from __future__ import annotations

import argparse
import asyncio
import uuid

from forecast.db.session import get_session_factory
from forecast.scoring.service import ScoringService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score an existing dataset by ID.")
    parser.add_argument("dataset_id", help="Dataset UUID to score.")
    return parser.parse_args()


async def main_async(dataset_id: str) -> None:
    session_factory = get_session_factory()
    scoring_service = ScoringService()

    async with session_factory() as session:
        async with session.begin():
            results = await scoring_service.score_dataset(session, uuid.UUID(dataset_id))

    for result in results:
        print(
            f"{result.category}: similarity={result.cosine_similarity:.4f}, "
            f"benchmark={result.benchmark_eval:.4f}, final={result.final_score:.2f}"
        )


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args.dataset_id))


if __name__ == "__main__":
    main()
