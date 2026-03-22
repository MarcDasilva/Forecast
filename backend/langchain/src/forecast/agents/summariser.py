from __future__ import annotations

import csv
from io import StringIO
from statistics import mean
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import ValidationError

from forecast.config import Settings, get_settings
from forecast.embeddings.schemas import SummarySchema

SUMMARISER_SYSTEM_PROMPT = """
You are a civic data analyst embedded in a city planning AI system. You will
receive raw or semi-structured data from a municipal dataset. Your job is to
produce a structured JSON summary with exactly the following keys:

{
  "title": "<short descriptive title for this dataset>",
  "domain": "<one of: housing | transportation | healthcare | employment |
             placemaking | mixed | unknown>",
  "geography": "<city, region, or 'unknown'>",
  "time_period": "<year or date range, or 'unknown'>",
  "key_metrics": {
    "<metric_name>": <numeric_value_or_null>
  },
  "civic_relevance": "<2-4 sentences on why this data matters to a city planner
                       and which planning categories it most directly informs>",
  "data_quality_notes": "<1-2 sentences on completeness, recency, known gaps,
                          or reliability caveats>"
}

Return ONLY the JSON object. No markdown fencing, no preamble, no explanation.
If a field cannot be determined, use null. Never hallucinate numeric metrics -
only extract values explicitly present in the input data.
If the input is tabular, preserve the original metric names where possible and
prefer explicit numeric values from the normalized table content.
""".strip()

JSON_CORRECTION_PROMPT = (
    "Your previous response was not valid for the required schema. "
    "Return only the JSON object matching the required schema, nothing else."
)


class StructuredSummaryModel(Protocol):
    async def ainvoke(self, input: object, config: object | None = None, **kwargs: object) -> object:
        ...


class SummaryGenerationError(RuntimeError):
    """Raised when the summariser fails to produce a valid summary."""


def _try_parse_float(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_probably_csv(raw_text: str) -> bool:
    lines = [line for line in raw_text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    return "," in lines[0] and "," in lines[1]


def normalize_dataset_text(raw_text: str) -> str:
    stripped = raw_text.strip()
    if not is_probably_csv(stripped):
        return stripped

    reader = csv.DictReader(StringIO(stripped))
    rows = list(reader)
    fieldnames = reader.fieldnames or []
    if not rows or not fieldnames:
        return stripped

    numeric_columns: dict[str, list[float]] = {}
    categorical_columns: dict[str, list[str]] = {}
    for field in fieldnames:
        values = [row.get(field, "").strip() for row in rows if row.get(field, "").strip()]
        numeric_values = [_try_parse_float(value) for value in values]
        if values and all(value is not None for value in numeric_values):
            numeric_columns[field] = [value for value in numeric_values if value is not None]
        elif values:
            categorical_columns[field] = values

    lines = [
        "Detected CSV dataset.",
        f"Columns: {', '.join(fieldnames)}.",
        f"Row count: {len(rows)}.",
    ]

    for field, values in categorical_columns.items():
        unique_values = list(dict.fromkeys(values))
        if len(unique_values) <= 5:
            lines.append(f"{field}: {', '.join(unique_values)}.")

    if numeric_columns:
        lines.append("Numeric column aggregates:")
        for field, values in numeric_columns.items():
            lines.append(
                f"- {field}: avg={mean(values):g}, min={min(values):g}, max={max(values):g}."
            )

    lines.append("Sample rows:")
    for row in rows[:5]:
        row_parts = [f"{field}={row[field]}" for field in fieldnames if row.get(field)]
        lines.append(f"- {', '.join(row_parts)}")

    return "\n".join(lines)


def build_summary_messages(raw_text: str, *, correction: str | None = None) -> list[object]:
    normalized_text = normalize_dataset_text(raw_text)
    messages: list[object] = [
        SystemMessage(content=SUMMARISER_SYSTEM_PROMPT),
        HumanMessage(content=f"Dataset input:\n{normalized_text}"),
    ]
    if correction:
        messages.append(HumanMessage(content=correction))
    return messages


class SummariserService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        model: StructuredSummaryModel | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.configure_langsmith()
        if model is not None:
            self.model = model
        else:
            base_model = ChatOpenAI(
                model=self.settings.openai_chat_model,
                temperature=0.2,
                api_key=self.settings.openai_api_key_value(),
            )
            self.model = base_model.with_structured_output(
                SummarySchema,
                method="function_calling",
            )

    @traceable(name="dataset_summariser", run_type="chain")
    async def summarise_text(self, raw_text: str) -> SummarySchema:
        messages = build_summary_messages(raw_text)
        try:
            return await self._invoke_and_validate(messages)
        except (ValidationError, TypeError, ValueError):
            retry_messages = build_summary_messages(raw_text, correction=JSON_CORRECTION_PROMPT)
            try:
                return await self._invoke_and_validate(retry_messages)
            except (ValidationError, TypeError, ValueError) as second_error:
                raise SummaryGenerationError("Failed to generate a valid structured summary.") from second_error

    async def _invoke_and_validate(self, messages: list[object]) -> SummarySchema:
        result = await self.model.ainvoke(messages)
        if isinstance(result, SummarySchema):
            return result
        if isinstance(result, dict):
            return SummarySchema.model_validate(result)
        raise TypeError(f"Unexpected structured output type: {type(result).__name__}")
