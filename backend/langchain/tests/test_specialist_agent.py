from __future__ import annotations

from forecast.agents.specialist_agent import SpecialistAgentService, SpecialistAssessmentResult


class FakeDataService:
    async def get_category_scores(self) -> dict[str, float]:
        return {"housing": 11.2}

    async def get_dataset_summaries(self, category: str, limit: int = 5) -> list[dict[str, object]]:
        assert category == "housing"
        return [
            {
                "id": "dataset-1",
                "source_ref": "housing.csv",
                "category": "housing",
                "similarity": 0.72,
                "benchmark_eval": 0.61,
                "final_score": 10.98,
                "summary": {
                    "title": "Housing Supply Monitor",
                    "geography": "Waterloo Region",
                    "time_period": "2026",
                    "key_metrics": {"vacancy_rate": 3.9},
                    "civic_relevance": "Tracks supply and affordability pressure.",
                    "data_quality_notes": "Pilot sample.",
                },
            }
        ]


class FakeAssessmentChain:
    async def ainvoke(self, prompt):
        assert prompt[0][0] == "system"
        assert prompt[1][0] == "human"
        return SpecialistAssessmentResult(
            category="housing",
            score=68,
            status_label="In Progress",
            confidence=0.78,
            rationale="Housing supply is improving but affordability pressure remains elevated.",
            benchmark_highlights=["Vacancy is inside the target band."],
            recommendations=["Increase non-market housing starts."],
            supporting_evidence=["dataset-1 reports a 3.9% vacancy rate."],
            source_dataset_ids=["dataset-1"],
        )


class FakeRepository:
    def __init__(self) -> None:
        self.saved: dict[str, object] | None = None

    async def create_assessment(self, session, **kwargs):
        self.saved = kwargs
        return kwargs


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return FakeTransaction()


class FakeSessionFactory:
    def __call__(self):
        return FakeSession()


async def test_specialist_agent_run_persists_assessment() -> None:
    repository = FakeRepository()
    service = SpecialistAgentService(
        category="housing",
        data_service=FakeDataService(),
        repository=repository,
        session_factory=FakeSessionFactory(),
        assessment_chain=FakeAssessmentChain(),
    )

    result = await service.run()

    assert result.category == "housing"
    assert result.score == 68
    assert repository.saved is not None
    assert repository.saved["agent_name"] == "housing_specialist_agent"
    assert repository.saved["source_dataset_ids"] == ["dataset-1"]
