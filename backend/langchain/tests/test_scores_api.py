from __future__ import annotations

from fastapi.testclient import TestClient

from forecast.main import app


def test_scores_endpoint_exists() -> None:
    client = TestClient(app)
    response = client.get("/scores")

    assert response.status_code == 200
    body = response.json()
    assert "scores" in body
    assert "dataset_count" in body
    assert "last_updated" in body
