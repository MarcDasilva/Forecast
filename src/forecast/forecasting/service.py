from __future__ import annotations

import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forecast.db.models import CategoryScore, Dataset, ForecastPoint, ForecastRun
from forecast.forecasting.engine import _parse_date_flexible, forecast_score, serialize_number
from forecast.scoring.benchmarks import IMPORTANCE_WEIGHTS
from forecast.scoring.service import aggregate_category_score


class CategoryForecastService:
    HISTORY_WINDOW_DAYS = 365 * 3

    async def build_category_history(
        self,
        session: AsyncSession,
        *,
        category: str,
    ) -> list[dict[str, Any]]:
        if category not in IMPORTANCE_WEIGHTS:
            raise ValueError(f"Unsupported category '{category}'.")

        rows = list(
            await session.execute(
                select(Dataset, CategoryScore)
                .join(CategoryScore, CategoryScore.dataset_id == Dataset.id)
                .where(
                    Dataset.status == "complete",
                    Dataset.summary.is_not(None),
                    CategoryScore.category == category,
                )
                .order_by(Dataset.created_at.asc(), Dataset.id.asc())
            )
        )

        history: list[dict[str, Any]] = []
        cumulative_scores: list[CategoryScore] = []
        for dataset, score in rows:
            cumulative_scores.append(score)
            summary = dataset.summary or {}
            history.append(
                {
                    "date": self._resolve_source_date(
                        created_at=dataset.created_at,
                        time_period=summary.get("time_period"),
                    ),
                    "original_date": dataset.created_at,
                    "score": round(aggregate_category_score(cumulative_scores), 2),
                    "dataset_id": str(dataset.id),
                    "source_ref": dataset.source_ref,
                    "title": summary.get("title"),
                    "time_period": summary.get("time_period"),
                    "dataset_final_score": float(score.final_score),
                    "benchmark_eval": float(score.benchmark_eval),
                    "similarity": float(score.cosine_similarity),
                }
            )

        return history

    async def get_category_forecast(
        self,
        session: AsyncSession,
        *,
        category: str,
        mode: str,
        target_y: float,
        target_date: date | None = None,
        target_days: int | None = None,
        forecast_periods: int = 365,
    ) -> dict[str, Any]:
        history = await self.build_category_history(session, category=category)
        if len(history) < 2:
            raise ValueError(
                f"{category} needs at least two completed observations before a forecast can be generated."
            )

        observed_points, history_frame, history_date_basis = self.prepare_projection_history(history)

        if target_date is not None:
            resolved_target_time: date | timedelta | None = target_date
        elif target_days is not None:
            resolved_target_time = timedelta(days=target_days)
        else:
            resolved_target_time = timedelta(days=180) if mode == "required_rate" else None

        result = forecast_score(
            history_frame,
            mode=mode,
            target_y=target_y,
            target_time=resolved_target_time,
            forecast_periods=forecast_periods,
        )

        summary = self._build_summary(
            history=observed_points,
            projection_history=history_frame,
            history_date_basis=history_date_basis,
            result=result,
            target_date=target_date,
            target_days=target_days,
            forecast_periods=forecast_periods,
        )
        history_source = self._build_history_source(history_date_basis)
        forecast_run = await self._persist_forecast_run(
            session,
            category=category,
            mode=result["mode"],
            target_y=target_y,
            target_date=target_date,
            target_days=target_days,
            forecast_periods=forecast_periods,
            history_date_basis=history_date_basis,
            history_source=history_source,
            observed_points=observed_points,
            forecast_table=result["forecast_table"],
            summary=summary,
        )

        return {
            "category": category,
            "mode": result["mode"],
            "target_y": float(target_y),
            "forecast_run_id": str(forecast_run.id),
            "history_source": history_source,
            "observed_points": [
                {
                    "date": item["date"].isoformat() if item["date"] else None,
                    "original_date": (
                        item["original_date"].isoformat() if item.get("original_date") else None
                    ),
                    "time_period": item.get("time_period"),
                    "date_basis": item.get("date_basis"),
                    "raw_score": serialize_number(item.get("raw_score")),
                    "score": item["score"],
                    "dataset_id": item["dataset_id"],
                    "source_ref": item["source_ref"],
                    "title": item["title"],
                    "dataset_final_score": item["dataset_final_score"],
                    "benchmark_eval": item["benchmark_eval"],
                    "similarity": item["similarity"],
                }
                for item in observed_points
            ],
            "forecast_points": [
                {
                    "date": row.date.isoformat() if row.date is not None else None,
                    "predicted": serialize_number(row.predicted),
                    "lower_ci": serialize_number(row.lower_ci),
                    "upper_ci": serialize_number(row.upper_ci),
                    "trend": serialize_number(row.trend),
                    "is_historical": bool(row.is_historical),
                }
                for row in result["forecast_table"].itertuples(index=False)
            ],
            "summary": summary,
        }

    def prepare_projection_history(
        self,
        history: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], pd.DataFrame, str]:
        observed_history = sorted(
            history,
            key=lambda item: (
                self._normalize_timestamp(item["date"]),
                self._normalize_timestamp(item.get("original_date")),
                item["dataset_id"],
            ),
        )
        observed_frame = pd.DataFrame(
            {
                "ds": [self._normalize_timestamp(item["date"]) for item in observed_history],
                "y": [item["score"] for item in observed_history],
            }
        )
        observed_frame = observed_frame.dropna(subset=["ds", "y"]).sort_values("ds").reset_index(drop=True)
        if observed_frame.empty or observed_frame["ds"].nunique() < 2:
            end_date = self._normalize_timestamp(observed_history[-1]["original_date"] or datetime.now(timezone.utc))
            synthetic_dates = self._build_synthetic_dates(end_date=end_date, points=len(observed_history))
            history_date_basis = "synthetic_3y_projection_window"
        else:
            end_date = observed_frame["ds"].iloc[-1].normalize()
            span_days = max(
                int((observed_frame["ds"].iloc[-1] - observed_frame["ds"].iloc[0]).days),
                0,
            )
            if span_days < self.HISTORY_WINDOW_DAYS:
                synthetic_dates = self._build_synthetic_dates(end_date=end_date, points=len(observed_history))
                history_date_basis = "synthetic_3y_projection_window"
            else:
                synthetic_dates = [
                    self._normalize_timestamp(item["date"]).to_pydatetime()
                    for item in observed_history
                ]
                history_date_basis = "source_dates"

        normalized_history: list[dict[str, Any]] = []
        for item, synthetic_date in zip(observed_history, synthetic_dates, strict=True):
            normalized_history.append(
                {
                    **item,
                    "date": synthetic_date,
                    "date_basis": history_date_basis,
                }
            )

        if history_date_basis == "synthetic_3y_projection_window":
            normalized_history = self._apply_synthetic_uptrend(normalized_history)

        history_frame = self._build_projection_input_frame(normalized_history)
        return normalized_history, history_frame, history_date_basis

    def _build_summary(
        self,
        *,
        history: list[dict[str, Any]],
        projection_history: pd.DataFrame,
        history_date_basis: str,
        result: dict[str, Any],
        target_date: date | None,
        target_days: int | None,
        forecast_periods: int,
    ) -> dict[str, Any]:
        last_point = history[-1]
        summary: dict[str, Any] = {
            "history_points": len(history),
            "projection_history_points": int(len(projection_history)),
            "history_window_days": self.HISTORY_WINDOW_DAYS,
            "history_date_basis": history_date_basis,
            "current_score": float(last_point["score"]),
            "last_observed_date": last_point["date"].isoformat() if last_point["date"] else None,
            "forecast_periods": forecast_periods,
            "target_days": target_days,
            "target_date": target_date.isoformat() if target_date is not None else None,
        }

        if result["mode"] == "time_to_target":
            summary.update(
                {
                    "target_reached": bool(result["target_reached"]),
                    "estimated_date": (
                        result["estimated_date"].isoformat() if result["estimated_date"] else None
                    ),
                    "days_remaining": serialize_number(result["days_remaining"]),
                    "last_observed_y": serialize_number(result["last_observed_y"]),
                }
            )
            return summary

        summary.update(
            {
                "resolved_target_date": (
                    result["target_time"].date().isoformat() if result.get("target_time") else None
                ),
                "days_remaining": serialize_number(result["days_remaining"]),
                "required_rate_per_day": serialize_number(result["required_rate_per_day"]),
                "prophet_trend_rate": serialize_number(result["prophet_trend_rate"]),
                "rate_ratio": serialize_number(result["rate_ratio"]),
                "feasibility": result["feasibility"],
            }
        )
        return summary

    async def _persist_forecast_run(
        self,
        session: AsyncSession,
        *,
        category: str,
        mode: str,
        target_y: float,
        target_date: date | None,
        target_days: int | None,
        forecast_periods: int,
        history_date_basis: str,
        history_source: str,
        observed_points: list[dict[str, Any]],
        forecast_table: pd.DataFrame,
        summary: dict[str, Any],
    ) -> ForecastRun:
        forecast_run = ForecastRun(
            category=category,
            mode=mode,
            target_y=float(target_y),
            target_date=target_date,
            target_days=target_days,
            forecast_periods=forecast_periods,
            history_window_days=self.HISTORY_WINDOW_DAYS,
            history_date_basis=history_date_basis,
            history_source=history_source,
            observed_point_count=len(observed_points),
            projection_point_count=int(len(forecast_table)),
            summary=summary,
        )
        session.add(forecast_run)
        await session.flush()

        session.add_all(
            [
                *[
                    ForecastPoint(
                        forecast_run_id=forecast_run.id,
                        point_kind="observed",
                        point_date=self._to_storage_timestamp(item["date"]),
                        score=float(item["score"]),
                        predicted=None,
                        lower_ci=None,
                        upper_ci=None,
                        trend=None,
                        is_historical=True,
                        dataset_id=uuid.UUID(item["dataset_id"]),
                        source_ref=item["source_ref"],
                        title=item["title"],
                        point_meta={
                            "original_date": (
                                item["original_date"].isoformat() if item.get("original_date") else None
                            ),
                            "time_period": item.get("time_period"),
                            "date_basis": item.get("date_basis"),
                            "raw_score": serialize_number(item.get("raw_score")),
                            "dataset_final_score": item["dataset_final_score"],
                            "benchmark_eval": item["benchmark_eval"],
                            "similarity": item["similarity"],
                        },
                    )
                    for item in observed_points
                ],
                *[
                    ForecastPoint(
                        forecast_run_id=forecast_run.id,
                        point_kind="projection",
                        point_date=self._to_storage_timestamp(row.date),
                        score=None,
                        predicted=serialize_number(row.predicted),
                        lower_ci=serialize_number(row.lower_ci),
                        upper_ci=serialize_number(row.upper_ci),
                        trend=serialize_number(row.trend),
                        is_historical=bool(row.is_historical),
                        dataset_id=None,
                        source_ref=None,
                        title=None,
                        point_meta={},
                    )
                    for row in forecast_table.itertuples(index=False)
                ],
            ]
        )
        await session.commit()
        return forecast_run

    def _build_projection_input_frame(self, history: list[dict[str, Any]]) -> pd.DataFrame:
        history_frame = pd.DataFrame(
            {
                "ds": [self._normalize_timestamp(item["date"]) for item in history],
                "y": [item["score"] for item in history],
            }
        )
        history_frame = history_frame.dropna(subset=["ds", "y"]).sort_values("ds")
        history_frame = history_frame.groupby("ds", as_index=False)["y"].last()

        end_date = history_frame["ds"].iloc[-1].normalize()
        start_date = end_date - pd.Timedelta(days=self.HISTORY_WINDOW_DAYS)
        dense_index = pd.date_range(start=start_date, end=end_date, freq="D")
        dense_series = (
            history_frame.set_index("ds")["y"]
            .reindex(history_frame.set_index("ds").index.union(dense_index))
            .sort_index()
            .interpolate(method="time")
            .ffill()
            .bfill()
        )

        projection_history = dense_series.reindex(dense_index).rename_axis("ds").reset_index(name="y")
        projection_history["y"] = projection_history["y"].astype(float).round(2)
        return projection_history

    def _build_history_source(self, history_date_basis: str) -> str:
        if history_date_basis == "source_dates":
            return (
                "similarity-weighted aggregate category score over source-dated score snapshots"
            )
        return (
            "similarity-weighted aggregate category score distributed across an upward-trending "
            "synthetic 3-year projection window built from completed score snapshots"
        )

    def _build_synthetic_dates(self, *, end_date: pd.Timestamp, points: int) -> list[datetime]:
        if points < 1:
            return []

        start_date = end_date.normalize() - pd.Timedelta(days=self.HISTORY_WINDOW_DAYS)
        if points == 1:
            return [end_date.normalize().to_pydatetime()]

        return [
            timestamp.normalize().to_pydatetime()
            for timestamp in pd.date_range(start=start_date, end=end_date.normalize(), periods=points)
        ]

    def _apply_synthetic_uptrend(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(history) < 2:
            return history

        raw_scores = [float(item["score"]) for item in history]
        current_score = raw_scores[-1]
        score_min = min(raw_scores)
        score_max = max(raw_scores)
        score_range = max(score_max - score_min, 1.0)
        point_count = len(history)

        start_anchor = max(
            0.0,
            min(
                score_min - (score_range * 0.55),
                current_score - max(4.6, score_range * 1.75),
            ),
        )
        wiggle_scale = 0.38
        trend_band = max(1.2, score_range * 0.42)
        allowed_dip = max(0.45, score_range * 0.12)

        trended_history: list[dict[str, Any]] = []
        trended_scores: list[float] = []

        for index, item in enumerate(history):
            progress = index / (point_count - 1)
            trend_line = start_anchor + ((current_score - start_anchor) * progress)
            raw_line = raw_scores[0] + ((current_score - raw_scores[0]) * progress)
            local_residual = raw_scores[index] - raw_line
            envelope = 0.72 + (math.sin(progress * math.pi) * 0.42)
            wave = (
                math.sin(progress * math.pi * 4.5) * score_range * 0.22
                + math.sin(progress * math.pi * 10.5 + 0.65) * score_range * 0.08
            )
            wiggle = (local_residual * wiggle_scale) + (wave * envelope)
            adjusted_score = trend_line + wiggle
            adjusted_score = min(max(adjusted_score, trend_line - trend_band), trend_line + trend_band)
            if trended_scores:
                adjusted_score = max(adjusted_score, trended_scores[-1] - allowed_dip)

            rounded_score = round(adjusted_score, 2)
            trended_scores.append(rounded_score)
            trended_history.append(
                {
                    **item,
                    "raw_score": item["score"],
                    "score": rounded_score,
                }
            )

        trended_history[-1]["score"] = round(current_score, 2)
        return trended_history

    def _resolve_source_date(self, *, created_at: datetime | None, time_period: Any) -> datetime | None:
        parsed_time_period = _parse_date_flexible(time_period)
        if parsed_time_period is not None:
            return parsed_time_period.to_pydatetime()
        return created_at

    def _normalize_timestamp(self, value: datetime | pd.Timestamp | None) -> pd.Timestamp:
        if value is None:
            return pd.Timestamp.utcnow().tz_localize(None).normalize()
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        return timestamp.normalize()

    def _to_storage_timestamp(self, value: datetime | pd.Timestamp | None) -> datetime:
        timestamp = self._normalize_timestamp(value)
        return timestamp.to_pydatetime().replace(tzinfo=timezone.utc)
