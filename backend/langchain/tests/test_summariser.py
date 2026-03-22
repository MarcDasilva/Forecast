from __future__ import annotations

import pytest

from forecast.agents.summariser import (
    JSON_CORRECTION_PROMPT,
    SummariserService,
    build_summary_messages,
    normalize_dataset_text,
)
from forecast.config import Settings
from forecast.embeddings.schemas import SummarySchema


class FakeStructuredModel:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.calls: list[list[object]] = []

    async def ainvoke(self, input: object, config: object | None = None, **kwargs: object) -> object:
        assert isinstance(input, list)
        self.calls.append(input)
        if not self.outputs:
            raise RuntimeError("No more fake outputs configured.")
        return self.outputs.pop(0)


def test_build_summary_messages_includes_dataset_input() -> None:
    messages = build_summary_messages("Vacancy rate: 4.2")

    assert len(messages) == 2
    assert "civic data analyst" in messages[0].content
    assert "Dataset input:\nVacancy rate: 4.2" == messages[1].content


def test_normalize_dataset_text_rewrites_csv_into_metric_friendly_text() -> None:
    csv_text = "\n".join(
        [
            "city,reporting_period,hospital_beds_per_1000,emergency_response_time_min",
            "Toronto,2025-Q4,2.8,9.1",
            "Toronto,2025-Q4,3.2,7.9",
        ]
    )

    normalized = normalize_dataset_text(csv_text)

    assert "Detected CSV dataset." in normalized
    assert "Columns: city, reporting_period, hospital_beds_per_1000, emergency_response_time_min." in normalized
    assert "city: Toronto." in normalized
    assert "- hospital_beds_per_1000: avg=3, min=2.8, max=3.2." in normalized
    assert "Sample rows:" in normalized


@pytest.mark.asyncio
async def test_summariser_returns_valid_summary_on_first_try() -> None:
    fake_model = FakeStructuredModel(
        [
            SummarySchema(
                title="Housing Snapshot",
                domain="housing",
                geography="Toronto",
                time_period="2025",
                key_metrics={"vacancy_rate": 4.2},
                civic_relevance="Helps planners understand housing pressure.",
                data_quality_notes="Single dataset sample.",
            )
        ]
    )
    service = SummariserService(
        settings=Settings(openai_api_key="test-key", langsmith_tracing=False),
        model=fake_model,
    )

    result = await service.summarise_text("Vacancy rate: 4.2")

    assert result.title == "Housing Snapshot"
    assert len(fake_model.calls) == 1


@pytest.mark.asyncio
async def test_summariser_retries_with_correction_prompt() -> None:
    fake_model = FakeStructuredModel(
        [
            {"title": "Bad Summary"},
            {
                "title": "Housing Snapshot",
                "domain": "housing",
                "geography": "Toronto",
                "time_period": "2025",
                "key_metrics": {"vacancy_rate": 4.2},
                "civic_relevance": "Helps planners understand housing pressure.",
                "data_quality_notes": "Single dataset sample.",
            },
        ]
    )
    service = SummariserService(
        settings=Settings(openai_api_key="test-key", langsmith_tracing=False),
        model=fake_model,
    )

    result = await service.summarise_text("Vacancy rate: 4.2")

    assert result.domain == "housing"
    assert len(fake_model.calls) == 2
    retry_messages = fake_model.calls[1]
    assert retry_messages[-1].content == JSON_CORRECTION_PROMPT
