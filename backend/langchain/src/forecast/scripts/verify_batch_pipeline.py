from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select

from forecast.db.models import CategoryScore
from forecast.db.session import get_session_factory
from forecast.scripts.run_pipeline_file import run_pipeline


INPUT_DIR = Path("data/samples/generated")


@dataclass
class VerificationResult:
    path: str
    expected_category: str
    dataset_id: str
    summary_domain: str
    top_score_category: str
    top_score_value: float
    domain_match: bool
    top_score_match: bool


async def fetch_top_score_category(dataset_id: str) -> tuple[str, float]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        rows = list(
            await session.scalars(
                select(CategoryScore)
                .where(CategoryScore.dataset_id == dataset_id)
                .order_by(CategoryScore.final_score.desc(), CategoryScore.category.asc())
            )
        )
    if not rows:
        return "unknown", 0.0
    top = rows[0]
    return top.category, float(top.final_score)


async def main_async() -> None:
    files = sorted(INPUT_DIR.glob("*.csv"))
    if not files:
        raise ValueError("No generated CSV files found. Run generate_random_samples first.")

    results: list[VerificationResult] = []
    for path in files:
        expected_category = path.stem.rsplit("_", 1)[0]
        pipeline_result = await run_pipeline(str(path))
        dataset_id = str(pipeline_result["dataset_id"])
        summary_domain = str(pipeline_result["summary"]["domain"])
        top_score_category, top_score_value = await fetch_top_score_category(dataset_id)
        results.append(
            VerificationResult(
                path=str(path),
                expected_category=expected_category,
                dataset_id=dataset_id,
                summary_domain=summary_domain,
                top_score_category=top_score_category,
                top_score_value=round(top_score_value, 2),
                domain_match=summary_domain == expected_category,
                top_score_match=top_score_category == expected_category,
            )
        )

    domain_matches = sum(result.domain_match for result in results)
    score_matches = sum(result.top_score_match for result in results)

    print(f"files={len(results)}")
    print(f"summary_domain_matches={domain_matches}/{len(results)}")
    print(f"top_score_matches={score_matches}/{len(results)}")
    for result in results:
        print(asdict(result))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
