from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Domain = Literal[
    "housing",
    "transportation",
    "healthcare",
    "employment",
    "placemaking",
    "mixed",
    "unknown",
]


class SummarySchema(BaseModel):
    title: str
    domain: Domain = "unknown"
    geography: str | None = None
    time_period: str | None = None
    key_metrics: dict[str, float | None] = Field(default_factory=dict)
    civic_relevance: str
    data_quality_notes: str


class EmbeddingResult(BaseModel):
    embed_input: str
    embedding: list[float]
    model: str
