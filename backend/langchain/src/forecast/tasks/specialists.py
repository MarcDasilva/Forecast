from __future__ import annotations

from forecast.agents.context_loader import SPECIALIST_CATEGORIES, validate_category
from forecast.agents.specialist_agent import SpecialistAgentService
from forecast.tasks.pipeline import celery_app, settings


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


async def run_specialist_agent(category: str) -> dict[str, object]:
    normalized_category = validate_category(category)
    service = SpecialistAgentService(category=normalized_category)
    result = await service.run()
    return result.model_dump()


async def run_all_specialist_agents() -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for category in SPECIALIST_CATEGORIES:
        results.append(await run_specialist_agent(category))
    return results
