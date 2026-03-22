from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from forecast.api.datasets import router as datasets_router


class FakeSession:
    def __init__(self, dataset, score_rows):
        self.dataset = dataset
        self.score_rows = score_rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, dataset_id):
        if dataset_id == self.dataset.id:
            return self.dataset
        return None

    async def scalars(self, query):
        return self.score_rows

    async def flush(self):
        return None


class FakeSessionFactory:
    def __init__(self, dataset, score_rows):
        self.dataset = dataset
        self.score_rows = score_rows

    def __call__(self):
        return FakeSession(self.dataset, self.score_rows)


def make_dataset():
    return type(
        "DatasetRecord",
        (),
        {
            "id": uuid.uuid4(),
            "source_ref": "Original dataset name",
            "status": "complete",
            "input_type": "file",
            "summary": {
                "title": "Housing Snapshot",
                "geography": "Toronto",
                "time_period": "2025",
                "key_metrics": {"units": 42},
            },
            "error_msg": None,
        },
    )()


def make_score(category: str, final_score: float):
    return type(
        "ScoreRow",
        (),
        {
            "category": category,
            "final_score": final_score,
            "cosine_similarity": 0.75,
            "benchmark_eval": 0.55,
        },
    )()


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(datasets_router)
    return TestClient(app)


def test_patch_dataset_renames_summary_title(monkeypatch) -> None:
    dataset = make_dataset()
    score_rows = [make_score("housing", 61.0)]

    monkeypatch.setattr(
        "forecast.api.datasets.get_session_factory",
        lambda: FakeSessionFactory(dataset, score_rows),
    )

    client = make_client()
    response = client.patch(f"/datasets/{dataset.id}", json={"summary_title": "Renamed dataset"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "Renamed dataset"
    assert dataset.summary["title"] == "Renamed dataset"
    assert payload["source_ref"] == "Original dataset name"
    assert dataset.source_ref == "Original dataset name"
    assert payload["scores"]["housing"]["final_score"] == 61.0


def test_patch_dataset_rejects_blank_name(monkeypatch) -> None:
    dataset = make_dataset()

    monkeypatch.setattr(
        "forecast.api.datasets.get_session_factory",
        lambda: FakeSessionFactory(dataset, []),
    )

    client = make_client()
    response = client.patch(f"/datasets/{dataset.id}", json={"summary_title": "   "})

    assert response.status_code == 400
