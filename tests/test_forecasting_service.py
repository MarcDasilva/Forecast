from __future__ import annotations

from datetime import datetime, timezone

from forecast.forecasting.service import CategoryForecastService


def _build_history_point(*, index: int, date: datetime, score: float) -> dict[str, object]:
    return {
        "date": date,
        "original_date": date,
        "score": score,
        "dataset_id": f"00000000-0000-0000-0000-{index:012d}",
        "source_ref": f"source-{index}",
        "title": f"Dataset {index}",
        "time_period": None,
        "dataset_final_score": score,
        "benchmark_eval": score,
        "similarity": 0.9,
    }


def test_prepare_projection_history_stretches_narrow_history_to_three_year_window() -> None:
    service = CategoryForecastService()
    history = [
        _build_history_point(
            index=1,
            date=datetime(2026, 3, 22, 15, 36, tzinfo=timezone.utc),
            score=54.0,
        ),
        _build_history_point(
            index=2,
            date=datetime(2026, 3, 22, 16, 19, tzinfo=timezone.utc),
            score=61.0,
        ),
    ]

    normalized_history, projection_history, history_date_basis = service.prepare_projection_history(history)

    assert history_date_basis == "synthetic_3y_projection_window"
    assert len(normalized_history) == 2
    assert normalized_history[0]["score"] < normalized_history[-1]["score"]
    assert projection_history["ds"].iloc[-1].date().isoformat() == "2026-03-22"
    assert (projection_history["ds"].iloc[-1] - projection_history["ds"].iloc[0]).days == 1095
    assert len(projection_history) == service.HISTORY_WINDOW_DAYS + 1


def test_prepare_projection_history_keeps_real_long_span_dates() -> None:
    service = CategoryForecastService()
    history = [
        _build_history_point(
            index=1,
            date=datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc),
            score=40.0,
        ),
        _build_history_point(
            index=2,
            date=datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
            score=62.0,
        ),
    ]

    normalized_history, projection_history, history_date_basis = service.prepare_projection_history(history)

    assert history_date_basis == "source_dates"
    assert normalized_history[0]["date"].date().isoformat() == "2023-01-01"
    assert normalized_history[-1]["date"].date().isoformat() == "2026-03-22"
    assert projection_history["ds"].iloc[-1].date().isoformat() == "2026-03-22"


def test_prepare_projection_history_shapes_synthetic_history_into_general_uptrend() -> None:
    service = CategoryForecastService()
    history = [
        _build_history_point(
            index=1,
            date=datetime(2026, 3, 22, 15, 36, tzinfo=timezone.utc),
            score=51.12,
        ),
        _build_history_point(
            index=2,
            date=datetime(2026, 3, 22, 15, 50, tzinfo=timezone.utc),
            score=55.95,
        ),
        _build_history_point(
            index=3,
            date=datetime(2026, 3, 22, 16, 0, tzinfo=timezone.utc),
            score=52.19,
        ),
        _build_history_point(
            index=4,
            date=datetime(2026, 3, 22, 16, 19, tzinfo=timezone.utc),
            score=55.48,
        ),
    ]

    normalized_history, _, history_date_basis = service.prepare_projection_history(history)
    normalized_scores = [item["score"] for item in normalized_history]
    upward_steps = sum(
        1
        for previous, current in zip(normalized_scores, normalized_scores[1:])
        if current >= previous
    )

    assert history_date_basis == "synthetic_3y_projection_window"
    assert normalized_scores[0] < normalized_scores[-1]
    assert upward_steps >= 2
    assert normalized_scores[0] <= 49.5
