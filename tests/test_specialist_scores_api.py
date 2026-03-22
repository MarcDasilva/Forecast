from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from forecast.main import app


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


def make_record(category: str, score: float):
    return type(
        "Record",
        (),
        {
            "id": uuid.uuid4(),
            "category": category,
            "agent_name": f"{category}_specialist_agent",
            "score": score,
            "status_label": "In Progress",
            "confidence": 0.8,
            "rationale": f"{category} rationale",
            "benchmark_highlights": [f"{category} highlight"],
            "recommendations": [f"{category} recommendation"],
            "supporting_evidence": [f"{category} evidence"],
            "source_dataset_ids": [f"{category}-1"],
            "created_at": datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
        },
    )()


def test_specialist_scores_endpoint_exists(monkeypatch) -> None:
    async def fake_latest(self, session):
        return [make_record("housing", 68.0), make_record("healthcare", 54.0)]

    monkeypatch.setattr(
        "forecast.api.specialist_scores.SpecialistAssessmentRepository.list_latest_assessments",
        fake_latest,
    )
    monkeypatch.setattr(
        "forecast.api.specialist_scores.get_session_factory",
        lambda: FakeSessionFactory(),
    )

    client = TestClient(app)
    response = client.get("/specialist-scores")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scores"]["housing"]["score"] == 68.0
    assert payload["scores"]["healthcare"]["score"] == 54.0
    assert payload["scores"]["employment"] is None


def test_specialist_score_history_endpoint_exists(monkeypatch) -> None:
    async def fake_list(self, session, *, category: str | None = None, limit: int = 20):
        assert category == "housing"
        return [make_record("housing", 68.0), make_record("housing", 62.0)]

    monkeypatch.setattr(
        "forecast.api.specialist_scores.SpecialistAssessmentRepository.list_assessments",
        fake_list,
    )
    monkeypatch.setattr(
        "forecast.api.specialist_scores.get_session_factory",
        lambda: FakeSessionFactory(),
    )

    client = TestClient(app)
    response = client.get("/specialist-scores/housing?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["category"] == "housing"
    assert payload["current"]["score"] == 68.0
    assert len(payload["history"]) == 2
