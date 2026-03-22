from __future__ import annotations

import asyncio

from forecast.tasks import specialists
from forecast.agents.specialist_agent import SpecialistAssessmentResult


async def test_run_all_specialist_agents_runs_in_parallel_in_eager_mode(monkeypatch) -> None:
    categories = ["housing", "employment", "transportation"]
    active = 0
    max_active = 0

    async def fake_run(category: str) -> dict[str, object]:
        nonlocal active, max_active

        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"category": category}

    monkeypatch.setattr(specialists, "SPECIALIST_CATEGORIES", categories)
    monkeypatch.setattr(specialists.settings, "celery_task_always_eager", True)
    monkeypatch.setattr(specialists, "run_specialist_agent", fake_run)

    results = await specialists.run_all_specialist_agents()

    assert [result["category"] for result in results] == categories
    assert max_active > 1


async def test_run_all_specialist_agents_dispatches_parallel_worker_group(monkeypatch) -> None:
    categories = ["housing", "employment", "transportation"]
    captured_categories: list[str] = []
    captured_get_kwargs: dict[str, object] = {}

    class FakeSignature:
        def __init__(self, category: str) -> None:
            self.category = category

    class FakeTask:
        def s(self, category: str) -> FakeSignature:
            return FakeSignature(category)

    class FakeAsyncResult:
        def get(self, **kwargs):
            captured_get_kwargs.update(kwargs)
            return [{"category": category} for category in captured_categories]

    class FakeGroup:
        def __init__(self, signatures) -> None:
            captured_categories.extend(signature.category for signature in signatures)

        def apply_async(self) -> FakeAsyncResult:
            return FakeAsyncResult()

    def fake_group(signatures):
        return FakeGroup(signatures)

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(specialists, "SPECIALIST_CATEGORIES", categories)
    monkeypatch.setattr(specialists.settings, "celery_task_always_eager", False)
    monkeypatch.setattr(specialists.settings, "specialist_agent_run_timeout_seconds", 123)
    monkeypatch.setattr(specialists, "group", fake_group)
    monkeypatch.setattr(specialists, "run_specialist_agent_task", FakeTask())
    monkeypatch.setattr(specialists.asyncio, "to_thread", fake_to_thread)

    results = await specialists.run_all_specialist_agents()

    assert results == [{"category": category} for category in categories]
    assert captured_categories == categories
    assert captured_get_kwargs == {
        "timeout": 123,
        "propagate": True,
        "disable_sync_subtasks": False,
    }


async def test_run_specialist_agent_combines_multiple_housing_profiles(monkeypatch) -> None:
    class FakeSpecialistAgentService:
        saved: tuple[SpecialistAssessmentResult, str | None] | None = None

        def __init__(self, *, category: str, agent_name: str | None = None, prompt_addendum: str | None = None, **kwargs) -> None:
            self.category = category
            self.agent_name = agent_name
            self.prompt_addendum = prompt_addendum

        async def evaluate(self) -> SpecialistAssessmentResult:
            score = 68 if self.prompt_addendum is None else 63
            rationale = "Base housing outlook is improving." if self.prompt_addendum is None else "Affordability pressure still warrants caution."
            return SpecialistAssessmentResult(
                category=self.category,
                score=score,
                status_label="In Progress",
                confidence=0.8,
                rationale=rationale,
                benchmark_highlights=["Housing supply signal"],
                recommendations=["Accelerate approvals"],
                supporting_evidence=["dataset-1"],
                source_dataset_ids=["dataset-1"],
            )

        async def persist_result(
            self,
            result: SpecialistAssessmentResult,
            *,
            agent_name: str | None = None,
        ) -> None:
            type(self).saved = (result, agent_name)

    monkeypatch.setattr(specialists, "SpecialistAgentService", FakeSpecialistAgentService)

    result = await specialists.run_specialist_agent("housing")

    assert result["category"] == "housing"
    assert result["score"] == 65.5
    assert result["status_label"] == "In Progress"
    assert "Base housing outlook is improving." in result["rationale"]
    assert "Affordability pressure still warrants caution." in result["rationale"]
    assert FakeSpecialistAgentService.saved is not None
    assert FakeSpecialistAgentService.saved[1] == "housing_specialist_ensemble"


async def test_run_specialist_agent_combines_multiple_employment_profiles(monkeypatch) -> None:
    class FakeSpecialistAgentService:
        saved: tuple[SpecialistAssessmentResult, str | None] | None = None

        def __init__(self, *, category: str, agent_name: str | None = None, prompt_addendum: str | None = None, **kwargs) -> None:
            self.category = category
            self.agent_name = agent_name
            self.prompt_addendum = prompt_addendum

        async def evaluate(self) -> SpecialistAssessmentResult:
            score = 66 if self.prompt_addendum is None else 61
            rationale = (
                "Base employment outlook remains stable."
                if self.prompt_addendum is None
                else "Wage pressure and inequality still warrant caution."
            )
            return SpecialistAssessmentResult(
                category=self.category,
                score=score,
                status_label="In Progress",
                confidence=0.79,
                rationale=rationale,
                benchmark_highlights=["Employment signal"],
                recommendations=["Expand living-wage coverage"],
                supporting_evidence=["dataset-2"],
                source_dataset_ids=["dataset-2"],
            )

        async def persist_result(
            self,
            result: SpecialistAssessmentResult,
            *,
            agent_name: str | None = None,
        ) -> None:
            type(self).saved = (result, agent_name)

    monkeypatch.setattr(specialists, "SpecialistAgentService", FakeSpecialistAgentService)

    result = await specialists.run_specialist_agent("employment")

    assert result["category"] == "employment"
    assert result["score"] == 63.5
    assert result["status_label"] == "In Progress"
    assert "Base employment outlook remains stable." in result["rationale"]
    assert "Wage pressure and inequality still warrant caution." in result["rationale"]
    assert FakeSpecialistAgentService.saved is not None
    assert FakeSpecialistAgentService.saved[1] == "employment_specialist_ensemble"
