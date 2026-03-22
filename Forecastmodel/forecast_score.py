"""
forecast_score.py — Single-function time-series forecasting with Prophet.

Supports two modes:
  "time_to_target"  — how long until score reaches target_y?
  "required_rate"   — what daily rate is needed to hit target_y by target_time?
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", message=".*Importing plotly.*")
warnings.filterwarnings("ignore", category=FutureWarning)

import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from datetime import datetime, timedelta
from typing import Union

from prophet import Prophet


# ── Type aliases ──────────────────────────────────────────────────────────────
DataInput    = Union[str, Path, pd.DataFrame]
TimeInput    = Union[str, pd.Timestamp, datetime, timedelta, None]
ForecastResult = dict   # typed dict returned to the caller


def forecast_score(
    data_input: DataInput,
    mode: str,
    target_y: float,
    target_time: TimeInput = None,
    forecast_periods: int = 365,
    plot: bool = True,
    plot_title: str = "Score Forecast",
) -> ForecastResult:
    """
    Forecast a time-series score with Facebook Prophet and answer one of two
    planning questions:

    Parameters
    ----------
    data_input : str | Path | pd.DataFrame
        Path to a CSV file **or** a DataFrame.  Must contain columns:
          • ``ds`` — datetime (any parseable format)
          • ``y``  — numeric score
    mode : {"time_to_target", "required_rate"}
        ``"time_to_target"``
            Find the first forecasted date where ``y >= target_y`` and return
            the time delta from the last observed point.
        ``"required_rate"``
            Compute the constant daily rate needed to reach ``target_y`` by
            ``target_time``.  Compares that rate against Prophet's modelled
            trend to assess feasibility.
    target_y : float
        The desired score to reach.
    target_time : str | Timestamp | datetime | timedelta | None
        **Required** when ``mode == "required_rate"``.
        Accepted forms:
          • ISO date string ``"2026-12-31"``
          • ``pd.Timestamp`` / ``datetime`` object
          • ``timedelta`` offset from the last observed date (e.g. ``timedelta(days=180)``)
    forecast_periods : int, default 365
        How many future daily periods Prophet should generate.
    plot : bool, default True
        Whether to render a matplotlib figure.
    plot_title : str, default "Score Forecast"
        Title for the plot.

    Returns
    -------
    dict with keys depending on mode:

    ``"time_to_target"`` result keys:
      - ``mode``
      - ``target_y``
      - ``target_reached``       bool
      - ``estimated_date``       pd.Timestamp | None
      - ``time_delta``           timedelta | None
      - ``days_remaining``       float | None
      - ``last_observed_date``   pd.Timestamp
      - ``last_observed_y``      float
      - ``forecast_df``          full Prophet forecast DataFrame

    ``"required_rate"`` result keys:
      - ``mode``
      - ``target_y``
      - ``target_time``          pd.Timestamp
      - ``required_rate_per_day``  float
      - ``prophet_trend_rate``     float  (average daily trend slope)
      - ``rate_ratio``             float  (required / prophet)
      - ``feasibility``            "on track" | "aggressive" | "very aggressive" | "declining"
      - ``days_remaining``         float
      - ``current_y``              float
      - ``forecast_df``            full Prophet forecast DataFrame

    Raises
    ------
    TypeError
        If ``data_input`` is not a path-like or DataFrame.
    ValueError
        If required columns are missing, mode is unrecognised, or
        ``target_time`` is missing for "required_rate" mode.
    """

    # ── 1. Load & validate data ───────────────────────────────────────────────
    df = _load_data(data_input)

    # ── 2. Fit Prophet ────────────────────────────────────────────────────────
    model, forecast = _fit_and_forecast(df, forecast_periods)

    # ── 3. Dispatch on mode ───────────────────────────────────────────────────
    mode = mode.strip().lower()

    if mode == "time_to_target":
        result = _time_to_target(df, forecast, target_y)

    elif mode == "required_rate":
        if target_time is None:
            raise ValueError(
                "'target_time' is required when mode='required_rate'. "
                "Pass a date string, datetime, Timestamp, or timedelta."
            )
        result = _required_rate(df, forecast, target_y, target_time)

    else:
        raise ValueError(
            f"Unknown mode '{mode}'. Choose 'time_to_target' or 'required_rate'."
        )

    # ── 4. Build a clean forecast table for downstream use ──────────────────
    last_obs = df["ds"].iloc[-1]
    table = forecast[["ds", "yhat", "yhat_lower", "yhat_upper", "trend"]].copy()
    table["is_historical"] = table["ds"] <= last_obs
    table = table.rename(columns={"ds": "date", "yhat": "predicted",
                                  "yhat_lower": "lower_ci",
                                  "yhat_upper": "upper_ci"})
    result["forecast_table"] = table.reset_index(drop=True)

    # ── 5. Optional plot ──────────────────────────────────────────────────────
    if plot:
        _plot(df, forecast, result, target_y, plot_title)

    return result


# ── Core mode implementations ─────────────────────────────────────────────────

def _time_to_target(
    df: pd.DataFrame,
    forecast: pd.DataFrame,
    target_y: float,
) -> ForecastResult:
    """Find the first future date where the forecast crosses target_y."""
    last_date = df["ds"].iloc[-1]
    last_y    = df["y"].iloc[-1]

    # Only look at future rows (after the last observed point)
    future_fc = forecast[forecast["ds"] > last_date].copy()

    crossing = future_fc[future_fc["yhat"] >= target_y]

    if crossing.empty:
        print(
            f"[forecast_score] Target y={target_y:.2f} is not reached within "
            f"{len(future_fc)} forecast periods. Consider increasing forecast_periods."
        )
        return {
            "mode":               "time_to_target",
            "target_y":           target_y,
            "target_reached":     False,
            "estimated_date":     None,
            "time_delta":         None,
            "days_remaining":     None,
            "last_observed_date": last_date,
            "last_observed_y":    last_y,
            "forecast_df":        forecast,
        }

    estimated_date = crossing["ds"].iloc[0]
    delta          = estimated_date - last_date
    days           = delta.total_seconds() / 86_400

    print(
        f"[forecast_score] Target y={target_y:.2f} reached on "
        f"{estimated_date.date()}  ({days:.1f} days from last observation)"
    )

    return {
        "mode":               "time_to_target",
        "target_y":           target_y,
        "target_reached":     True,
        "estimated_date":     estimated_date,
        "time_delta":         delta,
        "days_remaining":     days,
        "last_observed_date": last_date,
        "last_observed_y":    last_y,
        "forecast_df":        forecast,
    }


def _required_rate(
    df: pd.DataFrame,
    forecast: pd.DataFrame,
    target_y: float,
    target_time: TimeInput,
) -> ForecastResult:
    """Compute required daily rate and compare it to Prophet's trend."""
    last_date = df["ds"].iloc[-1]
    current_y = df["y"].iloc[-1]

    # ── Resolve target_time to a Timestamp ────────────────────────────────────
    if isinstance(target_time, timedelta):
        resolved_time = last_date + target_time
    else:
        resolved_time = pd.Timestamp(target_time)

    if resolved_time <= last_date:
        raise ValueError(
            f"target_time ({resolved_time.date()}) must be after the last "
            f"observed date ({last_date.date()})."
        )

    # ── Required slope ────────────────────────────────────────────────────────
    days_remaining    = (resolved_time - last_date).total_seconds() / 86_400
    required_rate     = (target_y - current_y) / days_remaining

    # ── Prophet's average trend slope over the forecast horizon ──────────────
    # Use the trend component between last observed date and target_time
    trend_window = forecast[
        (forecast["ds"] >= last_date) & (forecast["ds"] <= resolved_time)
    ].copy()

    if len(trend_window) >= 2:
        # Fit a simple linear regression on the trend column
        x = (trend_window["ds"] - trend_window["ds"].iloc[0]).dt.total_seconds() / 86_400
        prophet_trend_rate = float(np.polyfit(x, trend_window["trend"], 1)[0])
    else:
        prophet_trend_rate = float("nan")

    # ── Feasibility assessment ────────────────────────────────────────────────
    if np.isnan(prophet_trend_rate):
        feasibility = "unknown"
        rate_ratio  = float("nan")
    elif required_rate <= 0 and prophet_trend_rate <= 0:
        feasibility = "declining"
        rate_ratio  = required_rate / prophet_trend_rate if prophet_trend_rate != 0 else float("nan")
    else:
        rate_ratio = required_rate / prophet_trend_rate if prophet_trend_rate > 0 else float("inf")
        if rate_ratio <= 1.1:
            feasibility = "on track"
        elif rate_ratio <= 1.75:
            feasibility = "aggressive"
        else:
            feasibility = "very aggressive"

    print(
        f"[forecast_score] Required rate: {required_rate:+.4f}/day  |  "
        f"Prophet trend: {prophet_trend_rate:+.4f}/day  |  "
        f"Feasibility: {feasibility.upper()}  (ratio={rate_ratio:.2f}x)"
    )

    return {
        "mode":                  "required_rate",
        "target_y":              target_y,
        "target_time":           resolved_time,
        "required_rate_per_day": required_rate,
        "prophet_trend_rate":    prophet_trend_rate,
        "rate_ratio":            rate_ratio,
        "feasibility":           feasibility,
        "days_remaining":        days_remaining,
        "current_y":             current_y,
        "forecast_df":           forecast,
    }


# ── Data loading ──────────────────────────────────────────────────────────────

# Quarter-string pattern: "2025-Q4", "Q4-2025", "2025Q4"
_QUARTER_RE = re.compile(
    r"(?:(\d{4})[^\dQ]*Q(\d))|(?:Q(\d)[^\dQ]*(\d{4}))", re.IGNORECASE
)
_QUARTER_START = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}

# Yearless date patterns: "10-Sep", "Sep-10", "10 Sep", "Sep 10"
_YEARLESS_RE = re.compile(
    r"^(\d{1,2})[\s\-]([A-Za-z]{3,9})$"   # "10-Sep" / "10 September"
    r"|^([A-Za-z]{3,9})[\s\-](\d{1,2})$", # "Sep-10" / "September 10"
    re.IGNORECASE,
)

def _parse_date_flexible(value, _today=None) -> "pd.Timestamp | None":
    """
    Parse a date value into a pd.Timestamp, handling:
      - Standard ISO / locale strings  ("2025-09-10", "Sep 10 2025")
      - Quarterly labels               ("2025-Q4", "Q3 2024")
      - Year-less day-month strings    ("10-Sep", "Sep-10")
        → year inferred as most recent past occurrence
      - Existing Timestamp / datetime objects

    Returns None if the value cannot be parsed.
    """
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(value)
        # Guard against out-of-bounds years (pandas ns precision: 1677–2262)
        if ts.year < 1678 or ts.year > 2261:
            return None
        return ts

    s = str(value).strip()
    if not s:
        return None

    # ── Quarterly label ───────────────────────────────────────────────────────
    m = _QUARTER_RE.search(s)
    if m:
        year = int(m.group(1) or m.group(4))
        qnum = int(m.group(2) or m.group(3))
        return pd.Timestamp(f"{year}-{_QUARTER_START.get(qnum, '01-01')}")

    # ── Year-less "DD-Mon" or "Mon-DD" ────────────────────────────────────────
    m = _YEARLESS_RE.match(s)
    if m:
        if m.group(1):                       # "10-Sep"
            day, mon = m.group(1), m.group(2)
        else:                                # "Sep-10"
            mon, day = m.group(3), m.group(4)
        today = _today or datetime.today()
        # Try current year; fall back to previous year if date is in the future
        for year_offset in (0, -1, 1):
            try:
                ts = pd.Timestamp(f"{today.year + year_offset}-{mon}-{day}")
                if ts <= pd.Timestamp(today):
                    return ts
            except Exception:
                continue
        return None

    # ── Dot-separated M.D.YYYY  (e.g. "9.10.2022" → Sep 10 2022) ────────────
    dot_m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if dot_m:
        month, day, year = dot_m.group(1), dot_m.group(2), dot_m.group(3)
        try:
            ts = pd.Timestamp(f"{year}-{month.zfill(2)}-{day.zfill(2)}")
            return ts
        except Exception:
            return None

    # ── Standard date string ──────────────────────────────────────────────────
    try:
        ts = pd.Timestamp(s)
        if ts.year < 1678 or ts.year > 2261:
            return None
        return ts
    except Exception:
        return None


def _load_data(data_input: DataInput) -> pd.DataFrame:
    """Load, validate, clean, and sort the input data."""
    # ── Accept file path or DataFrame ─────────────────────────────────────────
    if isinstance(data_input, (str, Path)):
        path = Path(data_input)
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {path}")
        df = pd.read_csv(path)
        # Drop completely empty columns (common with trailing commas in CSV)
        df = df.dropna(axis=1, how="all")
        df.columns = df.columns.str.strip()
    elif isinstance(data_input, pd.DataFrame):
        df = data_input.copy()
    else:
        raise TypeError(
            f"data_input must be a file path or DataFrame, got {type(data_input).__name__}."
        )

    # ── Validate required columns ─────────────────────────────────────────────
    missing = {"ds", "y"} - set(df.columns)
    if missing:
        raise ValueError(
            f"Input data is missing required column(s): {missing}. "
            "Expected 'ds' (datetime) and 'y' (numeric score)."
        )

    # ── Type coercion ─────────────────────────────────────────────────────────
    df["ds"] = df["ds"].apply(_parse_date_flexible)
    df["y"]  = pd.to_numeric(df["y"], errors="coerce")

    # ── Drop rows where we have no usable data ────────────────────────────────
    n_before = len(df)
    df = df.dropna(subset=["ds", "y"])
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        print(f"[forecast_score] Dropped {n_dropped} row(s) with missing ds/y values.")

    # ── Aggregate duplicate dates (e.g. multiple facilities per period) ───────
    n_unique = df["ds"].nunique()
    if n_unique < len(df):
        print(
            f"[forecast_score] {len(df)} rows but only {n_unique} unique dates — "
            "aggregating by mean per date."
        )
        df = df.groupby("ds", as_index=False)["y"].mean()

    if n_unique < 2:
        raise ValueError(
            f"Only {n_unique} unique date(s) found after parsing. "
            "Prophet needs at least 2 distinct time points.\n"
            "Tip: your CSV may have multiple rows per period (e.g. one per facility). "
            "Make sure DS_COL points to a date column that varies across rows, "
            "or supply a CSV with multiple time periods."
        )

    # ── Sort chronologically ──────────────────────────────────────────────────
    df = df.sort_values("ds").reset_index(drop=True)

    return df[["ds", "y"]]


# ── Model fitting ─────────────────────────────────────────────────────────────

def _fit_and_forecast(
    df: pd.DataFrame,
    forecast_periods: int,
) -> tuple[Prophet, pd.DataFrame]:
    """Fit a Prophet model and return (model, forecast_df)."""

    # Detect average spacing between data points to tune Prophet accordingly.
    # Sparse data (e.g. one point per year) should behave like linear
    # regression — seasonality is meaningless and changepoints add noise.
    sorted_dates = df["ds"].sort_values()
    avg_gap_days = (sorted_dates.diff().dt.days.mean()) if len(df) > 1 else 1

    if avg_gap_days > 180:
        # Sparse / annual-ish data → linear trend, no seasonality
        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=False,
            daily_seasonality=False,
            seasonality_mode="additive",
            interval_width=0.90,
            changepoint_prior_scale=0.001,   # very rigid → near-linear
            n_changepoints=0,                # no changepoints at all
            growth="linear",
        )
    elif avg_gap_days > 14:
        # Monthly-ish data → yearly seasonality only, moderate flexibility
        model = Prophet(
            yearly_seasonality="auto",
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=0.90,
            changepoint_prior_scale=0.05,
        )
    else:
        # Dense daily/weekly data → full auto
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

    future   = model.make_future_dataframe(periods=forecast_periods, freq="D")
    forecast = model.predict(future)

    return model, forecast


# ── Plotting ──────────────────────────────────────────────────────────────────

def _plot(
    df: pd.DataFrame,
    forecast: pd.DataFrame,
    result: ForecastResult,
    target_y: float,
    title: str,
) -> None:
    """Render historical data, forecast, confidence intervals, and target."""
    fig, ax = plt.subplots(figsize=(13, 6))

    last_obs_date = df["ds"].iloc[-1]

    # ── Confidence band ───────────────────────────────────────────────────────
    ax.fill_between(
        forecast["ds"],
        forecast["yhat_lower"],
        forecast["yhat_upper"],
        alpha=0.15,
        color="#4C72B0",
        label="90% confidence interval",
    )

    # ── Forecast line ─────────────────────────────────────────────────────────
    future_fc = forecast[forecast["ds"] > last_obs_date]
    ax.plot(
        future_fc["ds"], future_fc["yhat"],
        color="#4C72B0", linewidth=1.8, linestyle="--", label="Forecast",
    )

    # ── Historical actuals ──────────────────────────────────────────���─────────
    hist_fc = forecast[forecast["ds"] <= last_obs_date]
    ax.plot(
        hist_fc["ds"], hist_fc["yhat"],
        color="#4C72B0", linewidth=1.8, alpha=0.6, label="Fitted trend",
    )
    ax.scatter(
        df["ds"], df["y"],
        color="black", s=18, zorder=5, alpha=0.7, label="Observed",
    )

    # ── Target line ───────────────────────────────────────────────────────────
    ax.axhline(
        target_y, color="#DD4444", linewidth=1.4,
        linestyle=":", label=f"Target y = {target_y:.2f}",
    )

    # ── Mode-specific annotation ──────────────────────────────────────────────
    mode = result["mode"]

    if mode == "time_to_target" and result["target_reached"]:
        est = result["estimated_date"]
        ax.axvline(est, color="#DD4444", linewidth=1.2, linestyle="--", alpha=0.7)
        ax.annotate(
            f"Reaches target\n{est.strftime('%b %d, %Y')}",
            xy=(est, target_y),
            xytext=(20, -40), textcoords="offset points",
            arrowprops=dict(arrowstyle="->", color="#DD4444"),
            fontsize=9, color="#DD4444",
        )

    elif mode == "required_rate":
        ttime = result["target_time"]
        ax.axvline(ttime, color="#228B22", linewidth=1.4, linestyle="--", alpha=0.8)
        ax.annotate(
            f"Target date\n{ttime.strftime('%b %d, %Y')}\n({result['feasibility'].upper()})",
            xy=(ttime, target_y),
            xytext=(-100, 20), textcoords="offset points",
            arrowprops=dict(arrowstyle="->", color="#228B22"),
            fontsize=9, color="#228B22",
        )
        # Draw the required straight-line rate
        cur_date = df["ds"].iloc[-1]
        cur_y    = result["current_y"]
        ax.plot(
            [cur_date, ttime], [cur_y, target_y],
            color="#228B22", linewidth=1.5, linestyle="-.",
            label=f"Required rate ({result['required_rate_per_day']:+.3f}/day)",
        )

    # ── Vertical separator: history vs forecast ───────────────────────────────
    ax.axvline(
        last_obs_date, color="grey", linewidth=0.8, linestyle=":", alpha=0.6
    )
    ax.text(
        last_obs_date, ax.get_ylim()[0],
        "  last obs.", fontsize=7, color="grey", va="bottom",
    )

    # ── Formatting — pick tick density/format based on total date span ────────
    all_dates = forecast["ds"]
    span_days  = (all_dates.max() - all_dates.min()).days

    if span_days > 365 * 3:          # multi-year: label each year
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    elif span_days > 180:            # 6 months–3 years: "Jan '25"
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    else:                            # short range: show month + day
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    fig.autofmt_xdate(rotation=30)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Score", fontsize=11)
    ax.legend(fontsize=9, loc="best")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.grid(axis="x", linestyle=":", alpha=0.3)

    plt.tight_layout()
    plt.show()


# ── Example usage ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    # ── Build a synthetic dataset (no hardcoded values — generated randomly) ──
    np.random.seed(42)
    dates  = pd.date_range("2023-01-01", periods=365, freq="D")
    trend  = np.linspace(40, 72, 365)
    noise  = np.random.normal(0, 2.5, 365)
    season = 4 * np.sin(2 * np.pi * np.arange(365) / 90)
    scores = trend + noise + season

    sample_df = pd.DataFrame({"ds": dates, "y": scores})

    # Save to CSV so we can demonstrate both input types
    csv_path = "/tmp/sample_scores.csv"
    sample_df.to_csv(csv_path, index=False)

    print("=" * 60)
    print("Example 1 — time_to_target  (CSV path input)")
    print("=" * 60)
    result1 = forecast_score(
        data_input      = csv_path,          # CSV file
        mode            = "time_to_target",
        target_y        = 85.0,
        forecast_periods= 730,               # forecast 2 years ahead
        plot            = True,
        plot_title      = "Score Forecast — Time to Target",
    )
    print(f"  target_reached : {result1['target_reached']}")
    print(f"  estimated_date : {result1['estimated_date']}")
    print(f"  days_remaining : {result1['days_remaining']:.1f}" if result1["days_remaining"] else "  (not reached)")

    print()
    print("=" * 60)
    print("Example 2 — required_rate  (DataFrame input + timedelta)")
    print("=" * 60)
    result2 = forecast_score(
        data_input      = sample_df,         # DataFrame
        mode            = "required_rate",
        target_y        = 85.0,
        target_time     = timedelta(days=180),  # 6 months from last data point
        forecast_periods= 365,
        plot            = True,
        plot_title      = "Score Forecast — Required Rate",
    )
    print(f"  required_rate_per_day  : {result2['required_rate_per_day']:+.4f}")
    print(f"  prophet_trend_rate     : {result2['prophet_trend_rate']:+.4f}")
    print(f"  rate_ratio             : {result2['rate_ratio']:.2f}x")
    print(f"  feasibility            : {result2['feasibility'].upper()}")

    print()
    print("=" * 60)
    print("Example 3 — required_rate  (ISO date string target_time)")
    print("=" * 60)
    result3 = forecast_score(
        data_input      = sample_df,
        mode            = "required_rate",
        target_y        = 90.0,
        target_time     = "2025-06-30",      # ISO date string
        forecast_periods= 730,
        plot            = True,
        plot_title      = "Score Forecast — Rate to 90 by Jun 2025",
    )
    print(f"  required_rate_per_day  : {result3['required_rate_per_day']:+.4f}")
    print(f"  feasibility            : {result3['feasibility'].upper()}")
