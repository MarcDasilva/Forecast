from __future__ import annotations

from fastapi.testclient import TestClient

from forecast.main import app


def test_ingest_requires_exactly_one_input(monkeypatch) -> None:
    client = TestClient(app)
    response = client.post("/ingest")

    assert response.status_code == 400


def test_datasets_endpoint_exists() -> None:
    client = TestClient(app)
    response = client.get("/datasets")

    assert response.status_code == 200
    assert "items" in response.json()
