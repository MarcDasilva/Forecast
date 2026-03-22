from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from forecast.api.datasets import router as datasets_router
from forecast.api.ingest import router as ingest_router


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(ingest_router)
    return TestClient(app)


def make_datasets_client() -> TestClient:
    app = FastAPI()
    app.include_router(datasets_router)
    return TestClient(app)


def test_ingest_requires_exactly_one_input(monkeypatch) -> None:
    client = make_client()
    response = client.post("/ingest")

    assert response.status_code == 400


def test_ingest_accepts_interview_transcript(monkeypatch) -> None:
    captured: dict[str, str] = {}
    queued_ids: list[str] = []
    dataset_id = uuid.uuid4()

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeSessionFactory:
        def __call__(self):
            return FakeSession()

    async def fake_create_dataset(
        self,
        session,
        *,
        input_type: str,
        source_ref: str,
        raw_text: str | None = None,
        summary=None,
        status: str = "pending",
    ):
        captured["input_type"] = input_type
        captured["source_ref"] = source_ref
        captured["raw_text"] = raw_text or ""
        captured["status"] = status
        return type("DatasetRecord", (), {"id": dataset_id})()

    async def fake_enqueue_dataset_processing(next_dataset_id: str) -> None:
        queued_ids.append(next_dataset_id)

    monkeypatch.setattr("forecast.api.ingest.get_session_factory", lambda: FakeSessionFactory())
    monkeypatch.setattr("forecast.api.ingest.DatasetRepository.create_dataset", fake_create_dataset)
    monkeypatch.setattr("forecast.api.ingest.enqueue_dataset_processing", fake_enqueue_dataset_processing)

    client = make_client()
    response = client.post(
        "/ingest",
        data={
            "transcript_text": "Interviewer: What is the top housing issue?\nResident: Affordability.",
            "label": "Tenant interview",
        },
    )

    assert response.status_code == 200
    assert response.json()["dataset_id"] == str(dataset_id)
    assert queued_ids == [str(dataset_id)]
    assert captured["input_type"] == "transcript"
    assert captured["source_ref"] == "Tenant interview"
    assert "SOURCE TYPE: interview transcript" in captured["raw_text"]
    assert "Resident: Affordability." in captured["raw_text"]
    assert captured["status"] == "pending"


def test_datasets_endpoint_exists(monkeypatch) -> None:
    class FakeDatasetSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def scalars(self, query):
            return []

        async def scalar(self, query):
            return 0

    class FakeDatasetSessionFactory:
        def __call__(self):
            return FakeDatasetSession()

    monkeypatch.setattr(
        "forecast.api.datasets.get_session_factory",
        lambda: FakeDatasetSessionFactory(),
    )

    client = make_datasets_client()
    response = client.get("/datasets")

    assert response.status_code == 200
    assert "items" in response.json()
