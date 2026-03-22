from __future__ import annotations

import json

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


async def test_employment_specialist_agent_includes_fred_macro_context() -> None:
    class FakeEmploymentDataService:
        async def get_category_scores(self) -> dict[str, float]:
            return {"employment": 63.5}

        async def get_dataset_summaries(self, category: str, limit: int = 5) -> list[dict[str, object]]:
            assert category == "employment"
            return [
                {
                    "id": "dataset-2",
                    "source_ref": "employment.csv",
                    "category": "employment",
                    "similarity": 0.88,
                    "benchmark_eval": 0.71,
                    "final_score": 63.5,
                    "summary": {
                        "title": "Regional Labour Market Snapshot",
                        "geography": "Waterloo Region",
                        "time_period": "2026-Q1",
                        "key_metrics": {"unemployment_rate": 5.1},
                        "civic_relevance": "Tracks labour-force conditions and wages.",
                        "data_quality_notes": "Compiled from pilot reporting.",
                    },
                }
            ]

    class FakeMacroContextProvider:
        async def build_context(self) -> dict[str, object]:
            return {
                "source": "fred_mcp",
                "available": True,
                "tool_calls": [
                    {"name": "tools/list", "ok": True},
                    {
                        "name": "fred_search",
                        "ok": True,
                        "selected_series_id": "LRUNTTTTCAM156S",
                    },
                    {
                        "name": "fred_get_series",
                        "ok": True,
                        "series_id": "LRUNTTTTCAM156S",
                    },
                ],
                "indicators": [
                    {
                        "indicator": "canada_unemployment_rate",
                        "series_id": "LRUNTTTTCAM156S",
                        "latest_value": 6.1,
                        "latest_date": "2026-01-01",
                        "summary": "Canada unemployment rate latest 6.1 on 2026-01-01.",
                    }
                ],
                "summary_lines": ["Canada unemployment rate latest 6.1 on 2026-01-01."],
                "errors": [],
            }

    class InspectingAssessmentChain:
        async def ainvoke(self, prompt):
            snapshot = json.loads(prompt[1][1].split("Evidence snapshot:\n", 1)[1])
            macro_context = snapshot["external_macro_context"]
            assert macro_context["source"] == "fred_mcp"
            assert macro_context["tool_calls"][1]["name"] == "fred_search"
            assert macro_context["tool_calls"][2]["name"] == "fred_get_series"
            assert macro_context["indicators"][0]["series_id"] == "LRUNTTTTCAM156S"
            return SpecialistAssessmentResult(
                category="employment",
                score=64,
                status_label="In Progress",
                confidence=0.75,
                rationale="Local employment is stable, with FRED macro context showing modest labour slack.",
                benchmark_highlights=["Macro context is now included."],
                recommendations=["Expand workforce attachment programs."],
                supporting_evidence=["FRED Canada unemployment series was reviewed."],
                source_dataset_ids=["dataset-2"],
            )

    repository = FakeRepository()
    service = SpecialistAgentService(
        category="employment",
        data_service=FakeEmploymentDataService(),
        repository=repository,
        session_factory=FakeSessionFactory(),
        assessment_chain=InspectingAssessmentChain(),
        macro_context_provider=FakeMacroContextProvider(),
    )

    result = await service.run()

    assert result.category == "employment"
    assert result.score == 64
    assert repository.saved is not None
    assert repository.saved["agent_name"] == "employment_specialist_agent"
