from __future__ import annotations

import asyncio
from dataclasses import dataclass

from celery import group

from forecast.agents.context_loader import SPECIALIST_CATEGORIES, validate_category
from forecast.agents.specialist_agent import (
    SpecialistAgentService,
    SpecialistAssessmentResult,
    merge_unique_items,
    status_label_for_score,
)
from forecast.tasks.pipeline import celery_app, settings


@dataclass(frozen=True)
class SpecialistProfile:
    agent_name: str
    prompt_addendum: str | None = None


HOUSING_CONSERVATIVE_PROMPT = """
Apply a slightly more conservative housing risk lens.
- Pay extra attention to affordability strain, delivery bottlenecks, and unmet need.
- If the evidence is mixed, land a few points below a neutral baseline rather than above it.
""".strip()

EMPLOYMENT_CONSERVATIVE_PROMPT = """
Apply a slightly more conservative employment resilience lens.
- Pay extra attention to wage pressure, uneven labour-force attachment, and inequality.
- If the evidence is mixed, land a few points below a neutral baseline rather than above it.
""".strip()


SPECIALIST_PROFILES: dict[str, tuple[SpecialistProfile, ...]] = {
    "housing": (
        SpecialistProfile(agent_name="housing_specialist_agent"),
        SpecialistProfile(
            agent_name="housing_affordability_pressure_specialist_agent",
            prompt_addendum=HOUSING_CONSERVATIVE_PROMPT,
        ),
    ),
    "employment": (
        SpecialistProfile(agent_name="employment_specialist_agent"),
        SpecialistProfile(
            agent_name="employment_wage_pressure_specialist_agent",
            prompt_addendum=EMPLOYMENT_CONSERVATIVE_PROMPT,
        ),
    ),
}


def _build_specialist_beat_schedule() -> dict[str, dict[str, object]]:
    interval_seconds = settings.specialist_agent_interval_minutes * 60
    return {
        f"run-{category}-specialist-agent": {
            "task": "forecast.run_specialist_agent",
            "schedule": interval_seconds,
            "args": (category,),
        }
        for category in SPECIALIST_CATEGORIES
    }


if settings.specialist_agent_interval_minutes > 0:
    celery_app.conf.beat_schedule = {
        **getattr(celery_app.conf, "beat_schedule", {}),
        **_build_specialist_beat_schedule(),
    }


@celery_app.task(name="forecast.run_specialist_agent")
def run_specialist_agent_task(category: str) -> dict[str, object]:
    import asyncio

    return asyncio.run(run_specialist_agent(category))


@celery_app.task(name="forecast.run_all_specialist_agents")
def run_all_specialist_agents_task() -> list[dict[str, object]]:
    import asyncio

    return asyncio.run(run_all_specialist_agents())


def get_specialist_profiles(category: str) -> tuple[SpecialistProfile, ...]:
    return SPECIALIST_PROFILES.get(
        category,
        (SpecialistProfile(agent_name=f"{category}_specialist_agent"),),
    )


def combine_specialist_results(
    category: str,
    results: list[SpecialistAssessmentResult],
) -> SpecialistAssessmentResult:
    average_score = round(sum(result.score for result in results) / len(results), 2)
    average_confidence = round(sum(result.confidence for result in results) / len(results), 3)
    rationale = " ".join(result.rationale.strip() for result in results if result.rationale.strip())

    return SpecialistAssessmentResult(
        category=category,
        score=average_score,
        status_label=status_label_for_score(average_score),
        confidence=average_confidence,
        rationale=rationale,
        benchmark_highlights=merge_unique_items(
            *(result.benchmark_highlights for result in results),
            limit=5,
        ),
        recommendations=merge_unique_items(
            *(result.recommendations for result in results),
            limit=3,
        ),
        supporting_evidence=merge_unique_items(
            *(result.supporting_evidence for result in results),
            limit=5,
        ),
        source_dataset_ids=merge_unique_items(
            *(result.source_dataset_ids for result in results),
            limit=5,
        ),
    )


async def run_specialist_agent(category: str) -> dict[str, object]:
    normalized_category = validate_category(category)
    profiles = get_specialist_profiles(normalized_category)

    if len(profiles) == 1:
        service = SpecialistAgentService(
            category=normalized_category,
            agent_name=profiles[0].agent_name,
            prompt_addendum=profiles[0].prompt_addendum,
        )
        result = await service.run()
        return result.model_dump()

    services = [
        SpecialistAgentService(
            category=normalized_category,
            agent_name=profile.agent_name,
            prompt_addendum=profile.prompt_addendum,
        )
        for profile in profiles
    ]
    profile_results = await asyncio.gather(*(service.evaluate() for service in services))
    combined_result = combine_specialist_results(normalized_category, profile_results)
    await services[0].persist_result(
        combined_result,
        agent_name=f"{normalized_category}_specialist_ensemble",
    )
    return combined_result.model_dump()


async def run_all_specialist_agents() -> list[dict[str, object]]:
    if settings.celery_task_always_eager:
        tasks = [run_specialist_agent(category) for category in SPECIALIST_CATEGORIES]
        return list(await asyncio.gather(*tasks))

    job = group(run_specialist_agent_task.s(category) for category in SPECIALIST_CATEGORIES).apply_async()
    return list(
        await asyncio.to_thread(
            job.get,
            timeout=settings.specialist_agent_run_timeout_seconds,
            propagate=True,
            disable_sync_subtasks=False,
        )
    )
