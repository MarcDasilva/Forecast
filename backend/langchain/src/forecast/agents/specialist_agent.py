from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any

from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import BaseModel, Field

from forecast.agents.context_loader import load_category_context, validate_category
from forecast.agents.data_service import AgentDataService
from forecast.agents.fred_mcp import EmploymentMacroContextProvider
from forecast.config import Settings, get_settings
from forecast.db.repositories import SpecialistAssessmentRepository
from forecast.db.session import get_session_factory

STATUS_GUIDANCE = """
Score bands:
- 0-24: Critical
- 25-49: Needs Attention
- 50-74: In Progress
- 75-89: Strong
- 90-100: Leading
""".strip()


class SpecialistAssessmentResult(BaseModel):
    category: str
    score: float = Field(ge=0, le=100)
    status_label: str
    confidence: float = Field(ge=0, le=1)
    rationale: str
    benchmark_highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    source_dataset_ids: list[str] = Field(default_factory=list)


def status_label_for_score(score: float) -> str:
    if score < 25:
        return "Critical"
    if score < 50:
        return "Needs Attention"
    if score < 75:
        return "In Progress"
    if score < 90:
        return "Strong"
    return "Leading"


def merge_unique_items(*collections: list[str], limit: int) -> list[str]:
    ordered: OrderedDict[str, None] = OrderedDict()
    for collection in collections:
        for item in collection:
            if item and item not in ordered:
                ordered[item] = None
            if len(ordered) >= limit:
                return list(ordered.keys())
    return list(ordered.keys())


class SpecialistAgentService:
    def __init__(
        self,
        *,
        category: str,
        agent_name: str | None = None,
        prompt_addendum: str | None = None,
        settings: Settings | None = None,
        data_service: AgentDataService | None = None,
        repository: SpecialistAssessmentRepository | None = None,
        session_factory: Any | None = None,
        assessment_chain: Any | None = None,
        macro_context_provider: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.configure_langsmith()
        self.category = validate_category(category)
        self.context_text = load_category_context(self.category)
        self.agent_name = agent_name or f"{self.category}_specialist_agent"
        self.prompt_addendum = prompt_addendum.strip() if prompt_addendum else None
        self.data_service = data_service or AgentDataService(settings=self.settings)
        self.repository = repository or SpecialistAssessmentRepository()
        self.session_factory = session_factory or get_session_factory()
        self.macro_context_provider = macro_context_provider
        if self.macro_context_provider is None and self.category == "employment":
            self.macro_context_provider = EmploymentMacroContextProvider(settings=self.settings)
        self.assessment_chain = assessment_chain or self._build_assessment_chain()

    def _build_assessment_chain(self) -> Any:
        model = ChatOpenAI(
            model=self.settings.openai_chat_model,
            temperature=0.2,
            api_key=self.settings.openai_api_key_value(),
        )
        return model.with_structured_output(
            SpecialistAssessmentResult,
            method="function_calling",
        )

    def _build_prompt(self, resource_snapshot: dict[str, Any]) -> list[tuple[str, str]]:
        system_prompt = f"""
You are the dedicated {self.category} specialist agent for the Forecast civic scorecard.
Score only the {self.category} domain. Use the benchmark context below as the source of truth.

{STATUS_GUIDANCE}

Rules:
- Use only the supplied benchmark context and evidence snapshot.
- Generate a score from 0 to 100 for current performance in {self.category}.
- If evidence is limited, score conservatively and lower confidence.
- Keep rationale concise and evidence-backed.
- Recommendations must be specific and action-oriented.
- If external macro context is provided, treat it as a secondary signal alongside local evidence.

{self.prompt_addendum or ""}

Benchmark context:
{self.context_text}
""".strip()

        human_prompt = """
Evaluate the current category performance using the evidence snapshot below.

Return a structured assessment with:
- category
- score
- status_label
- confidence
- rationale
- benchmark_highlights
- recommendations
- supporting_evidence
- source_dataset_ids

Evidence snapshot:
{resource_snapshot}
""".strip().format(resource_snapshot=json.dumps(resource_snapshot, indent=2))

        return [("system", system_prompt), ("human", human_prompt)]

    async def _build_resource_snapshot(self) -> dict[str, Any]:
        aggregate_scores = await self.data_service.get_category_scores()
        category_datasets = await self.data_service.get_dataset_summaries(self.category, limit=5)
        snapshot = {
            "category": self.category,
            "current_aggregate_score": aggregate_scores.get(self.category, 0.0),
            "dataset_count": len(category_datasets),
            "datasets": [
                {
                    "id": dataset["id"],
                    "source_ref": dataset["source_ref"],
                    "similarity": dataset["similarity"],
                    "benchmark_eval": dataset["benchmark_eval"],
                    "final_score": dataset["final_score"],
                    "summary": {
                        "title": dataset["summary"].get("title"),
                        "geography": dataset["summary"].get("geography"),
                        "time_period": dataset["summary"].get("time_period"),
                        "key_metrics": dataset["summary"].get("key_metrics", {}),
                        "civic_relevance": dataset["summary"].get("civic_relevance"),
                        "data_quality_notes": dataset["summary"].get("data_quality_notes"),
                    },
                }
                for dataset in category_datasets
            ],
        }
        if self.macro_context_provider is not None:
            snapshot["external_macro_context"] = await self.macro_context_provider.build_context()
        return snapshot

    @traceable(name="specialist_agent_run", run_type="chain")
    async def evaluate(self) -> SpecialistAssessmentResult:
        resource_snapshot = await self._build_resource_snapshot()
        prompt = self._build_prompt(resource_snapshot)
        result = await self.assessment_chain.ainvoke(prompt)

        return SpecialistAssessmentResult(
            category=self.category,
            score=result.score,
            status_label=result.status_label,
            confidence=result.confidence,
            rationale=result.rationale,
            benchmark_highlights=result.benchmark_highlights[:5],
            recommendations=result.recommendations[:3],
            supporting_evidence=result.supporting_evidence[:5],
            source_dataset_ids=result.source_dataset_ids[:5],
        )

    async def persist_result(
        self,
        result: SpecialistAssessmentResult,
        *,
        agent_name: str | None = None,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await self.repository.create_assessment(
                    session,
                    category=result.category,
                    agent_name=agent_name or self.agent_name,
                    score=result.score,
                    status_label=result.status_label,
                    confidence=result.confidence,
                    rationale=result.rationale,
                    benchmark_highlights=result.benchmark_highlights,
                    recommendations=result.recommendations,
                    supporting_evidence=result.supporting_evidence,
                    source_dataset_ids=result.source_dataset_ids,
                )

    async def run(self) -> SpecialistAssessmentResult:
        normalized = await self.evaluate()
        await self.persist_result(normalized)
        return normalized
