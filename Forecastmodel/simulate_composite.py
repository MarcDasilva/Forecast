"""
simulate_composite.py — Composite score simulation & decision-support tool.

A composite score is a weighted sum of N subcategory scores that each evolve
over time.  This module lets you ask:

  "If I push each subcategory toward a target at a certain pace,
   what is the resulting composite rate and when do I hit my goal?"

The heavy lifting (Prophet fitting, rate computation) is delegated entirely
to the existing ``forecast_score`` function — this module orchestrates the
subcategory calls, combines their rates with weights, and produces a
unified result + visualisation.
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", message=".*Importing plotly.*")
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from typing import Union

from forecast_score import forecast_score, DataInput, TimeInput


# ── Type aliases ──────────────────────────────────────────────────────────────
SubcategoryData   = dict[str, DataInput]           # name → DataFrame or CSV path
Weights           = dict[str, float]               # name → weight
Targets           = dict[str, float]               # name → target score
TargetTimes       = dict[str, TimeInput]           # name → deadline
CompositeResult   = dict                           # structured output


def simulate_composite_score(
    subcategory_data: SubcategoryData,
    weights: Weights,
    mode: str,
    composite_target: float | None = None,
    sub_targets: Targets | None = None,
    sub_target_times: TargetTimes | None = None,
    forecast_periods: int = 365,
    plot: bool = True,
) -> CompositeResult:
    """
    Simulate how individually-targeted subcategory improvements combine
    into an overall composite score trajectory.

    Parameters
    ----------
    subcategory_data : dict[str, DataFrame | str]
        Mapping of subcategory name → time-series data (DataFrame or CSV
        path).  Each must contain ``ds`` (datetime) and ``y`` (score).
        Exactly 5 subcategories are required.

    weights : dict[str, float]
        Mapping of subcategory name → weight.  Keys must match
        ``subcategory_data``.  Values must sum to 1.0.

    mode : {"composite_rate", "composite_time_to_target"}
        ``"composite_rate"``
            Compute the weighted composite rate of change and show each
            subcategory's contribution.
        ``"composite_time_to_target"``
            Estimate when the composite score will reach
            ``composite_target`` given the subcategory rates.

    composite_target : float | None
        Required when ``mode == "composite_time_to_target"``.
        The desired composite score.

    sub_targets : dict[str, float]
        Target score for each subcategory.  Required for both modes
        (used to compute each subcategory's required rate).

    sub_target_times : dict[str, TimeInput]
        Deadline for each subcategory target.  Required for both modes.
        Accepts any format that ``forecast_score`` understands: ISO date
        strings, ``pd.Timestamp``, ``datetime``, or ``timedelta``.

    forecast_periods : int, default 365
        Passed through to ``forecast_score`` for each subcategory.

    plot : bool, default True
        Render a multi-panel visualisation.

    Returns
    -------
    dict with keys:
        mode                 str
        composite_rate       float   — weighted dS/dt (per day)
        current_composite    float   — S₀ = Σ wᵢ · sᵢ(latest)
        subcategory_rates    dict    — {name: rate_per_day}
        contributions        dict    — {name: wᵢ · rate_per_day}
        feasibility          dict    — {name: feasibility_label}
        sub_results          dict    — {name: full forecast_score result}

      Additional keys when mode == "composite_time_to_target":
        composite_target     float
        time_to_target_days  float | None
        estimated_date       Timestamp | None
        target_reached       bool

    Raises
    ------
    ValueError
        Validation failures (wrong count, bad weights, missing args).
    """

    # ── 1. Validate inputs ────────────────────────────────────────────────────
    _validate(subcategory_data, weights, mode, composite_target,
              sub_targets, sub_target_times)

    names = list(subcategory_data.keys())
    mode  = mode.strip().lower()

    # ── 2. Run forecast_score("required_rate") for every subcategory ──────────
    sub_results: dict[str, dict] = {}
    sub_rates:   dict[str, float] = {}
    sub_current: dict[str, float] = {}
    sub_feasibility: dict[str, str] = {}

    for name in names:
        print(f"\n{'─'*50}")
        print(f"  Subcategory: {name}  (weight={weights[name]:.2f})")
        print(f"{'─'*50}")

        result = forecast_score(
            data_input      = subcategory_data[name],
            mode            = "required_rate",
            target_y        = sub_targets[name],
            target_time     = sub_target_times[name],
            forecast_periods= forecast_periods,
            plot            = False,          # we draw our own composite plot
        )

        sub_results[name] = result
        sub_current[name] = result["current_y"]

        # If the subcategory already meets/exceeds its target, the
        # "required_rate" is negative (it would need to *decrease*).
        # That's misleading — use the Prophet trend rate instead,
        # which reflects the subcategory's natural momentum.
        if result["current_y"] >= sub_targets[name]:
            sub_rates[name]       = result["prophet_trend_rate"]
            sub_feasibility[name] = "target met"
            print(f"  → Current ({result['current_y']:.2f}) already meets "
                  f"target ({sub_targets[name]:.2f}) — using trend rate.")
        else:
            sub_rates[name]       = result["required_rate_per_day"]
            sub_feasibility[name] = result["feasibility"]

    # ── 3. Composite calculations ─────────────────────────────────────────────
    # dS/dt = Σ wᵢ · (dsᵢ/dt)
    contributions = {n: weights[n] * sub_rates[n] for n in names}
    composite_rate = sum(contributions.values())

    # S₀ = Σ wᵢ · sᵢ(latest)
    current_composite = sum(weights[n] * sub_current[n] for n in names)

    # ── 4. Build result ───────────────────────────────────────────────────────
    output: CompositeResult = {
        "mode":              mode,
        "composite_rate":    composite_rate,
        "current_composite": current_composite,
        "subcategory_rates": sub_rates,
        "contributions":     contributions,
        "feasibility":       sub_feasibility,
        "sub_results":       sub_results,
    }

    if mode == "composite_time_to_target":
        if composite_rate <= 0:
            print(
                f"\n[composite] Composite rate is {composite_rate:+.4f}/day — "
                "target cannot be reached with current subcategory plans."
            )
            output.update({
                "composite_target":    composite_target,
                "time_to_target_days": None,
                "estimated_date":      None,
                "target_reached":      False,
            })
        else:
            gap  = composite_target - current_composite
            days = gap / composite_rate

            if days <= 0:
                # Already at or above target
                output.update({
                    "composite_target":    composite_target,
                    "time_to_target_days": 0.0,
                    "estimated_date":      pd.Timestamp.today().normalize(),
                    "target_reached":      True,
                })
            else:
                # Find a reference "now" from the latest subcategory observation
                latest_dates = [
                    sub_results[n].get("target_time", pd.Timestamp.today())
                    for n in names
                ]
                # Use last observed date from any subcategory as the anchor
                anchor_dates = []
                for n in names:
                    fc = sub_results[n].get("forecast_df")
                    if fc is not None:
                        data_end = fc["ds"].min()  # just use the result's reference
                    anchor_dates.append(sub_results[n].get("target_time", pd.Timestamp.today()))

                # Simplest anchor: use the latest data point across all subs
                last_obs_dates = []
                for n in names:
                    fc = sub_results[n]["forecast_df"]
                    last_obs_dates.append(fc["ds"].iloc[0])  # earliest in forecast

                # Actually pull from current_y's associated date
                # The forecast_df contains historical + future rows.
                # The last observed date per subcategory can be inferred from
                # the sub_results — specifically the target_time minus
                # days_remaining.  Simpler: just use the max of
                # (target_time - days_remaining) across subs.
                ref_dates = []
                for n in names:
                    r = sub_results[n]
                    if r.get("target_time") and r.get("days_remaining"):
                        ref_dates.append(
                            r["target_time"] - timedelta(days=r["days_remaining"])
                        )
                ref_date = max(ref_dates) if ref_dates else pd.Timestamp.today().normalize()

                est_date = ref_date + timedelta(days=days)
                print(
                    f"\n[composite] Current={current_composite:.2f}  "
                    f"Target={composite_target:.2f}  "
                    f"Rate={composite_rate:+.4f}/day  →  "
                    f"{days:.1f} days  (est. {est_date.date()})"
                )
                output.update({
                    "composite_target":    composite_target,
                    "time_to_target_days": days,
                    "estimated_date":      est_date,
                    "target_reached":      True,
                })

    # ── 5. Build output tables ───────────────────────────────────────────────

    # summary_table: one row per subcategory + a COMPOSITE total row
    rows = []
    for n in names:
        rows.append({
            "subcategory":  n,
            "weight":       weights[n],
            "current_score": sub_current[n],
            "target_score": sub_targets[n],
            "rate_per_day": sub_rates[n],
            "contribution": contributions[n],
            "feasibility":  sub_feasibility[n],
        })
    rows.append({
        "subcategory":  "COMPOSITE",
        "weight":       1.0,
        "current_score": current_composite,
        "target_score": composite_target if mode == "composite_time_to_target" else None,
        "rate_per_day": composite_rate,
        "contribution": composite_rate,
        "feasibility":  None,
    })
    output["summary_table"] = pd.DataFrame(rows)

    # projection_table: daily time-series with composite + per-sub weighted scores
    ref_dates_list = []
    for n in names:
        r = sub_results[n]
        if r.get("target_time") and r.get("days_remaining"):
            ref_dates_list.append(
                r["target_time"] - timedelta(days=r["days_remaining"])
            )
    ref_date = max(ref_dates_list) if ref_dates_list else pd.Timestamp.today().normalize()

    projection_days = 365 * 2
    if output.get("time_to_target_days") and output["time_to_target_days"] > 0:
        projection_days = max(projection_days, int(output["time_to_target_days"] * 1.2))
    projection_days = min(projection_days, 365 * 20)

    days_arr = np.arange(0, projection_days + 1)
    proj = pd.DataFrame({"date": [ref_date + timedelta(days=int(d)) for d in days_arr]})
    proj["composite"] = current_composite + composite_rate * days_arr
    for n in names:
        proj[n] = sub_current[n] + sub_rates[n] * days_arr              # raw score
        proj[f"{n}_weighted"] = weights[n] * proj[n]                     # weighted
    output["projection_table"] = proj

    # ── 6. Print summary ──────────────────────────────────────────────────────
    _print_summary(output, names, weights, sub_current)

    # ── 7. Plot ───────────────────────────────────────────────────────────────
    if plot:
        _composite_plot(output, names, weights, sub_current, sub_results,
                        composite_target if mode == "composite_time_to_target" else None)

    return output


# ── Validation ────────────────────────────────────────────────────────────────

def _validate(
    subcategory_data, weights, mode, composite_target,
    sub_targets, sub_target_times,
) -> None:
    """Raise ValueError on any input violation."""
    names = set(subcategory_data.keys())

    if len(names) != 5:
        raise ValueError(
            f"Exactly 5 subcategories required, got {len(names)}: {names}"
        )

    if set(weights.keys()) != names:
        raise ValueError(
            f"Weight keys {set(weights.keys())} don't match "
            f"subcategory keys {names}."
        )

    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 1e-6:
        raise ValueError(
            f"Weights must sum to 1.0, got {weight_sum:.6f}."
        )

    mode = mode.strip().lower()
    if mode not in ("composite_rate", "composite_time_to_target"):
        raise ValueError(
            f"Unknown mode '{mode}'. "
            "Choose 'composite_rate' or 'composite_time_to_target'."
        )

    if mode == "composite_time_to_target" and composite_target is None:
        raise ValueError(
            "'composite_target' is required when mode='composite_time_to_target'."
        )

    if sub_targets is None:
        raise ValueError("'sub_targets' is required (target score per subcategory).")
    if set(sub_targets.keys()) != names:
        raise ValueError(
            f"sub_targets keys {set(sub_targets.keys())} don't match "
            f"subcategory keys {names}."
        )

    if sub_target_times is None:
        raise ValueError("'sub_target_times' is required (deadline per subcategory).")
    if set(sub_target_times.keys()) != names:
        raise ValueError(
            f"sub_target_times keys {set(sub_target_times.keys())} don't match "
            f"subcategory keys {names}."
        )


# ── Pretty-print ──────────────────────────────────────────────────────────────

def _print_summary(
    output: CompositeResult,
    names: list[str],
    weights: dict[str, float],
    sub_current: dict[str, float],
) -> None:
    """Print a formatted summary table to stdout."""
    print()
    print("=" * 70)
    print("  COMPOSITE SCORE SIMULATION — RESULTS")
    print("=" * 70)

    # Header
    print(f"  {'Subcategory':<20} {'Weight':>7} {'Current':>9} "
          f"{'Rate/day':>10} {'Contrib':>10} {'Feasibility':>15}")
    print(f"  {'─'*20} {'─'*7} {'─'*9} {'─'*10} {'─'*10} {'─'*15}")

    for n in names:
        w = weights[n]
        cur = sub_current[n]
        rate = output["subcategory_rates"][n]
        contrib = output["contributions"][n]
        feas = output["feasibility"][n]
        print(f"  {n:<20} {w:>7.2f} {cur:>9.2f} "
              f"{rate:>+10.4f} {contrib:>+10.4f} {feas:>15}")

    print(f"  {'─'*20} {'─'*7} {'─'*9} {'─'*10} {'─'*10} {'─'*15}")
    print(f"  {'COMPOSITE':<20} {'1.00':>7} "
          f"{output['current_composite']:>9.2f} "
          f"{'':>10} {output['composite_rate']:>+10.4f}")

    if output["mode"] == "composite_time_to_target":
        print()
        if output.get("target_reached"):
            print(f"  Target {output['composite_target']:.2f} reached in "
                  f"{output['time_to_target_days']:.1f} days  "
                  f"(est. {output['estimated_date'].date()})")
        else:
            print(f"  Target {output['composite_target']:.2f} NOT reachable "
                  "with current subcategory plans.")

    print("=" * 70)


# ── Visualisation ─────────────────────────────────────────────────────────────

_COLORS = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"]

def _composite_plot(
    output: CompositeResult,
    names: list[str],
    weights: dict[str, float],
    sub_current: dict[str, float],
    sub_results: dict[str, dict],
    composite_target: float | None,
) -> None:
    """Two-panel figure: subcategory trajectories + composite projection."""
    fig, (ax_sub, ax_comp) = plt.subplots(1, 2, figsize=(16, 6))

    # ── Left panel: subcategory rate contributions (bar chart) ────────────────
    contribs = output["contributions"]
    colors = {n: _COLORS[i % len(_COLORS)] for i, n in enumerate(names)}

    bars = ax_sub.barh(
        list(contribs.keys()),
        list(contribs.values()),
        color=[colors[n] for n in contribs],
        edgecolor="white",
        linewidth=0.8,
    )
    ax_sub.axvline(0, color="black", linewidth=0.6)
    ax_sub.set_xlabel("Weighted rate contribution (per day)", fontsize=10)
    ax_sub.set_title("Subcategory Contributions to dS/dt", fontsize=12,
                     fontweight="bold")

    # Annotate bars with rate and weight
    for bar, name in zip(bars, contribs):
        val = contribs[name]
        rate = output["subcategory_rates"][name]
        w = weights[name]
        label = f" {val:+.4f}  (rate={rate:+.4f} × w={w:.2f})"
        ax_sub.text(
            bar.get_width(), bar.get_y() + bar.get_height() / 2,
            label, va="center", fontsize=8,
            ha="left" if val >= 0 else "right",
        )

    ax_sub.grid(axis="x", linestyle="--", alpha=0.3)

    # ── Right panel: composite score projection over time ─────────────────────
    # Build a daily composite trajectory from the reference date forward
    # using the linear composite rate.
    ref_dates = []
    for n in names:
        r = sub_results[n]
        if r.get("target_time") and r.get("days_remaining"):
            ref_dates.append(
                r["target_time"] - timedelta(days=r["days_remaining"])
            )
    ref_date = max(ref_dates) if ref_dates else pd.Timestamp.today().normalize()

    # Determine how far to project
    projection_days = 365 * 2
    if output.get("time_to_target_days") and output["time_to_target_days"] > 0:
        projection_days = max(projection_days, int(output["time_to_target_days"] * 1.2))
    projection_days = min(projection_days, 365 * 20)  # cap at 20 years

    days_arr = np.arange(0, projection_days + 1)
    dates_arr = pd.to_datetime([ref_date + timedelta(days=int(d)) for d in days_arr])
    composite_arr = output["current_composite"] + output["composite_rate"] * days_arr

    ax_comp.plot(dates_arr, composite_arr, color="#4C72B0", linewidth=2,
                 label=f"Composite (rate={output['composite_rate']:+.4f}/day)")

    # Plot individual weighted subcategory trajectories
    for i, n in enumerate(names):
        sub_y = (sub_current[n] + output["subcategory_rates"][n] * days_arr) * weights[n]
        ax_comp.plot(dates_arr, sub_y, color=_COLORS[i % len(_COLORS)],
                     linewidth=1, alpha=0.5, linestyle="--",
                     label=f"{n} (weighted)")

    # Mark current composite
    ax_comp.scatter([ref_date], [output["current_composite"]],
                    color="black", s=60, zorder=5, label="Current composite")

    # Target line + estimated arrival
    if composite_target is not None:
        ax_comp.axhline(composite_target, color="#DD4444", linewidth=1.4,
                        linestyle=":", label=f"Target = {composite_target:.2f}")

        if output.get("estimated_date"):
            est = output["estimated_date"]
            ax_comp.axvline(est, color="#DD4444", linewidth=1, linestyle="--",
                            alpha=0.6)
            ax_comp.annotate(
                f"Reaches target\n{est.strftime('%b %d, %Y')}",
                xy=(est, composite_target),
                xytext=(15, -35), textcoords="offset points",
                arrowprops=dict(arrowstyle="->", color="#DD4444"),
                fontsize=9, color="#DD4444",
            )

    # Format x-axis
    span = (dates_arr[-1] - dates_arr[0]).days
    if span > 365 * 3:
        ax_comp.xaxis.set_major_locator(mdates.YearLocator())
        ax_comp.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    elif span > 180:
        ax_comp.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax_comp.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    else:
        ax_comp.xaxis.set_major_locator(mdates.MonthLocator())
        ax_comp.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))

    fig.autofmt_xdate(rotation=30)
    ax_comp.set_xlabel("Date", fontsize=10)
    ax_comp.set_ylabel("Composite Score", fontsize=10)
    ax_comp.set_title("Composite Score Projection", fontsize=12, fontweight="bold")
    ax_comp.legend(fontsize=8, loc="best")
    ax_comp.grid(axis="y", linestyle="--", alpha=0.3)
    ax_comp.grid(axis="x", linestyle=":", alpha=0.2)

    plt.tight_layout()
    plt.show()


# ── Example usage ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.getLogger("prophet").setLevel(logging.ERROR)
    logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

    # Generate 5 synthetic subcategory time series
    np.random.seed(42)
    base_dates = pd.date_range("2020-01-01", periods=7, freq="365D")

    def _make_sub(start, slope, noise=1.5):
        y = start + slope * np.arange(len(base_dates)) + np.random.normal(0, noise, len(base_dates))
        return pd.DataFrame({"ds": base_dates, "y": y})

    subcategory_data = {
        "healthcare":    _make_sub(45, 3.0),
        "education":     _make_sub(55, 2.0),
        "housing":       _make_sub(35, 4.0),
        "employment":    _make_sub(60, 1.5),
        "social_support": _make_sub(40, 2.5),
    }

    weights = {
        "healthcare":     0.25,
        "education":      0.20,
        "housing":        0.20,
        "employment":     0.20,
        "social_support": 0.15,
    }

    sub_targets = {
        "healthcare":     80.0,
        "education":      75.0,
        "housing":        75.0,
        "employment":     80.0,
        "social_support": 70.0,
    }

    sub_target_times = {
        "healthcare":     timedelta(days=365 * 3),
        "education":      timedelta(days=365 * 3),
        "housing":        timedelta(days=365 * 3),
        "employment":     timedelta(days=365 * 3),
        "social_support": timedelta(days=365 * 3),
    }

    print("\n" + "=" * 70)
    print("  EXAMPLE 1 — composite_rate")
    print("=" * 70)

    result1 = simulate_composite_score(
        subcategory_data = subcategory_data,
        weights          = weights,
        mode             = "composite_rate",
        sub_targets      = sub_targets,
        sub_target_times = sub_target_times,
        forecast_periods = 365 * 4,
        plot             = True,
    )

    print("\n" + "=" * 70)
    print("  EXAMPLE 2 — composite_time_to_target")
    print("=" * 70)

    result2 = simulate_composite_score(
        subcategory_data = subcategory_data,
        weights          = weights,
        mode             = "composite_time_to_target",
        composite_target = 78.0,
        sub_targets      = sub_targets,
        sub_target_times = sub_target_times,
        forecast_periods = 365 * 4,
        plot             = True,
    )
