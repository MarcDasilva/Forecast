from __future__ import annotations

from fastapi.testclient import TestClient

from forecast.main import app


def test_healthcheck_includes_cors_header_for_frontend_origin() -> None:
    client = TestClient(app)
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
