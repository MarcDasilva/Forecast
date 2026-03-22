from __future__ import annotations

from fastapi.testclient import TestClient

from forecast.main import app


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSessionFactory:
    def __call__(self):
        return FakeSession()


def test_scores_endpoint_exists(monkeypatch) -> None:
    async def fake_get_aggregated_scores(self, session):
        return {"housing": 61.2}, 4, None

    monkeypatch.setattr("forecast.api.scores.get_session_factory", lambda: FakeSessionFactory())
    monkeypatch.setattr(
        "forecast.api.scores.ScoringService.get_aggregated_scores",
        fake_get_aggregated_scores,
    )

    client = TestClient(app)
    response = client.get("/scores")

    assert response.status_code == 200
    body = response.json()
    assert "scores" in body
    assert "dataset_count" in body
    assert "last_updated" in body


def test_category_forecast_endpoint_exists(monkeypatch) -> None:
    async def fake_get_category_forecast(
        self,
        session,
        *,
        category: str,
        mode: str,
        target_y: float,
        target_date,
        target_days,
        forecast_periods: int,
    ):
        return {
            "category": category,
            "mode": mode,
            "target_y": target_y,
            "history_source": "test history",
            "observed_points": [{"date": "2026-01-01T00:00:00+00:00", "score": 58.0}],
            "forecast_points": [
                {
                    "date": "2026-01-01T00:00:00+00:00",
                    "predicted": 58.0,
                    "lower_ci": 55.0,
                    "upper_ci": 61.0,
                    "trend": 58.0,
                    "is_historical": True,
                }
            ],
            "summary": {
                "history_points": 3,
                "current_score": 58.0,
                "forecast_periods": forecast_periods,
                "target_days": target_days,
                "target_date": target_date.isoformat() if target_date else None,
            },
        }

    monkeypatch.setattr(
        "forecast.api.scores.CategoryForecastService.get_category_forecast",
        fake_get_category_forecast,
    )
    monkeypatch.setattr("forecast.api.scores.get_session_factory", lambda: FakeSessionFactory())

    client = TestClient(app)
    response = client.get(
        "/scores/forecast/housing",
        params={"mode": "required_rate", "target_y": 72, "target_days": 180, "forecast_periods": 365},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "housing"
    assert body["mode"] == "required_rate"
    assert body["summary"]["target_days"] == 180
    assert body["forecast_points"][0]["is_historical"] is True
