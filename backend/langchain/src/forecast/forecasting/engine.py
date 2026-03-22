from __future__ import annotations

import math
import logging
import re
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

DataInput = str | Path | pd.DataFrame
TimeInput = str | pd.Timestamp | datetime | timedelta | None
ForecastResult = dict[str, Any]

_QUARTER_RE = re.compile(
    r"(?:(\d{4})[^\dQ]*Q(\d))|(?:Q(\d)[^\dQ]*(\d{4}))", re.IGNORECASE
)
_QUARTER_START = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}
_YEARLESS_RE = re.compile(
    r"^(\d{1,2})[\s\-]([A-Za-z]{3,9})$|^([A-Za-z]{3,9})[\s\-](\d{1,2})$",
    re.IGNORECASE,
)


def forecast_score(
    data_input: DataInput,
    *,
    mode: str,
    target_y: float,
    target_time: TimeInput = None,
    forecast_periods: int = 365,
) -> ForecastResult:
    df = _load_data(data_input)
    _, forecast = _fit_and_forecast(df, forecast_periods)

    normalized_mode = mode.strip().lower()
    if normalized_mode == "time_to_target":
        result = _time_to_target(df, forecast, target_y)
    elif normalized_mode == "required_rate":
        if target_time is None:
            raise ValueError(
                "'target_time' is required when mode='required_rate'."
            )
        result = _required_rate(df, forecast, target_y, target_time)
    else:
        raise ValueError(
            f"Unknown mode '{mode}'. Choose 'time_to_target' or 'required_rate'."
        )

    last_observed = df["ds"].iloc[-1]
    table = forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "trend"]].copy()
    table["is_historical"] = table["ds"] <= last_observed
    table = table.rename(
        columns={
            "ds": "date",
            "yhat": "predicted",
            "yhat_lower": "lower_ci",
            "yhat_upper": "upper_ci",
        }
    )
    result["forecast_table"] = table.reset_index(drop=True)
    return result


def _time_to_target(
    df: pd.DataFrame,
    forecast: pd.DataFrame,
    target_y: float,
) -> ForecastResult:
    last_date = df["ds"].iloc[-1]
    last_y = df["y"].iloc[-1]
    future_forecast = forecast[forecast["ds"] > last_date].copy()
    crossing = future_forecast[future_forecast["yhat"] >= target_y]

    if crossing.empty:
        return {
            "mode": "time_to_target",
            "target_y": target_y,
            "target_reached": False,
            "estimated_date": None,
            "time_delta": None,
            "days_remaining": None,
            "last_observed_date": last_date,
            "last_observed_y": float(last_y),
            "forecast_df": forecast,
        }

    estimated_date = crossing["ds"].iloc[0]
    delta = estimated_date - last_date
    days_remaining = delta.total_seconds() / 86_400
    return {
        "mode": "time_to_target",
        "target_y": target_y,
        "target_reached": True,
        "estimated_date": estimated_date,
        "time_delta": delta,
        "days_remaining": days_remaining,
        "last_observed_date": last_date,
        "last_observed_y": float(last_y),
        "forecast_df": forecast,
    }


def _required_rate(
    df: pd.DataFrame,
    forecast: pd.DataFrame,
    target_y: float,
    target_time: TimeInput,
) -> ForecastResult:
    last_date = df["ds"].iloc[-1]
    current_y = df["y"].iloc[-1]

    if isinstance(target_time, timedelta):
        resolved_time = last_date + target_time
    else:
        resolved_time = pd.Timestamp(target_time)

    if resolved_time <= last_date:
        raise ValueError(
            f"target_time ({resolved_time.date()}) must be after the last observed date "
            f"({last_date.date()})."
        )

    days_remaining = (resolved_time - last_date).total_seconds() / 86_400
    required_rate = (target_y - current_y) / days_remaining

    trend_window = forecast[
        (forecast["ds"] >= last_date) & (forecast["ds"] <= resolved_time)
    ].copy()

    if len(trend_window) >= 2:
        x = (trend_window["ds"] - trend_window["ds"].iloc[0]).dt.total_seconds() / 86_400
        prophet_trend_rate = float(np.polyfit(x, trend_window["trend"], 1)[0])
    else:
        prophet_trend_rate = float("nan")

    if np.isnan(prophet_trend_rate):
        feasibility = "unknown"
        rate_ratio = float("nan")
    elif required_rate <= 0 and prophet_trend_rate <= 0:
        feasibility = "declining"
        rate_ratio = (
            required_rate / prophet_trend_rate if prophet_trend_rate != 0 else float("nan")
        )
    else:
        rate_ratio = required_rate / prophet_trend_rate if prophet_trend_rate > 0 else float("inf")
        if rate_ratio <= 1.1:
            feasibility = "on track"
        elif rate_ratio <= 1.75:
            feasibility = "aggressive"
        else:
            feasibility = "very aggressive"

    return {
        "mode": "required_rate",
        "target_y": target_y,
        "target_time": resolved_time,
        "required_rate_per_day": float(required_rate),
        "prophet_trend_rate": float(prophet_trend_rate),
        "rate_ratio": float(rate_ratio),
        "feasibility": feasibility,
        "days_remaining": days_remaining,
        "current_y": float(current_y),
        "forecast_df": forecast,
    }


def _parse_date_flexible(value: object, *, today: datetime | None = None) -> pd.Timestamp | None:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        timestamp = pd.Timestamp(value)
        if timestamp.year < 1678 or timestamp.year > 2261:
            return None
        return timestamp

    text = str(value).strip()
    if not text:
        return None

    quarter_match = _QUARTER_RE.search(text)
    if quarter_match:
        year = int(quarter_match.group(1) or quarter_match.group(4))
        quarter = int(quarter_match.group(2) or quarter_match.group(3))
        return pd.Timestamp(f"{year}-{_QUARTER_START.get(quarter, '01-01')}")

    yearless_match = _YEARLESS_RE.match(text)
    if yearless_match:
        if yearless_match.group(1):
            day, month = yearless_match.group(1), yearless_match.group(2)
        else:
            month, day = yearless_match.group(3), yearless_match.group(4)
        current = today or datetime.today()
        for offset in (0, -1, 1):
            try:
                timestamp = pd.Timestamp(f"{current.year + offset}-{month}-{day}")
            except Exception:
                continue
            if timestamp <= pd.Timestamp(current):
                return timestamp
        return None

    dotted_match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", text)
    if dotted_match:
        month, day, year = dotted_match.group(1), dotted_match.group(2), dotted_match.group(3)
        try:
            return pd.Timestamp(f"{year}-{month.zfill(2)}-{day.zfill(2)}")
        except Exception:
            return None

    try:
        timestamp = pd.Timestamp(text)
    except Exception:
        return None

    if timestamp.year < 1678 or timestamp.year > 2261:
        return None
    return timestamp


def _load_data(data_input: DataInput) -> pd.DataFrame:
    if isinstance(data_input, (str, Path)):
        path = Path(data_input)
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {path}")
        frame = pd.read_csv(path)
        frame = frame.dropna(axis=1, how="all")
        frame.columns = frame.columns.str.strip()
    elif isinstance(data_input, pd.DataFrame):
        frame = data_input.copy()
    else:
        raise TypeError(
            f"data_input must be a file path or DataFrame, got {type(data_input).__name__}."
        )

    missing = {"ds", "y"} - set(frame.columns)
    if missing:
        raise ValueError(
            f"Input data is missing required column(s): {missing}. "
            "Expected 'ds' (datetime) and 'y' (numeric score)."
        )

    frame["ds"] = frame["ds"].apply(_parse_date_flexible)
    frame["y"] = pd.to_numeric(frame["y"], errors="coerce")
    frame = frame.dropna(subset=["ds", "y"])

    unique_dates = frame["ds"].nunique()
    if unique_dates < len(frame):
        frame = frame.groupby("ds", as_index=False)["y"].mean()
        unique_dates = frame["ds"].nunique()

    if unique_dates < 2:
        raise ValueError(
            "At least two distinct observations are required to generate a forecast."
        )

    return frame.sort_values("ds").reset_index(drop=True)[["ds", "y"]]


def _fit_and_forecast(
    df: pd.DataFrame,
    forecast_periods: int,
) -> tuple[Any, pd.DataFrame]:
    try:
        from prophet import Prophet
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The forecasting feature requires the 'prophet' package to be installed."
        ) from exc

    sorted_dates = df["ds"].sort_values()
    avg_gap_days = sorted_dates.diff().dt.days.mean() if len(df) > 1 else 1

    if avg_gap_days > 180:
        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=False,
            daily_seasonality=False,
            seasonality_mode="additive",
            interval_width=0.90,
            changepoint_prior_scale=0.001,
            n_changepoints=0,
            growth="linear",
        )
    elif avg_gap_days > 14:
        model = Prophet(
            yearly_seasonality="auto",
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=0.90,
            changepoint_prior_scale=0.05,
        )
    else:
        model = Prophet(
            yearly_seasonality="auto",
            weekly_seasonality="auto",
            daily_seasonality=False,
            interval_width=0.90,
            changepoint_prior_scale=0.05,
        )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(df)

    future = model.make_future_dataframe(periods=forecast_periods, freq="D")
    forecast = model.predict(future)
    return model, forecast


def serialize_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and (math.isnan(value) or math.isinf(value)):
        return None
    return float(value)
