"""
run_composite.py — configure and run the composite score simulator.

Edit the CONFIG section below, then run:
    python3 run_composite.py
"""

import warnings
warnings.filterwarnings("ignore")
import logging
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

import pandas as pd
import numpy as np
from datetime import timedelta
from simulate_composite import simulate_composite_score

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG — edit this section
# ═══════════════════════════════════════════════════════════════════════════════

# ── Subcategory data (DataFrame or CSV path, each needs "ds" and "y") ─────────
# Replace with your real data / CSV paths. Below is synthetic demo data.
np.random.seed(42)
_dates = pd.date_range("2020-01-01", periods=7, freq="365D")

def _demo(start, slope, noise=1.5):
    y = start + slope * np.arange(len(_dates)) + np.random.normal(0, noise, len(_dates))
    return pd.DataFrame({"ds": _dates, "y": y})

SUBCATEGORY_DATA = {
    "healthcare":     _demo(45, 2.5),
    "education":      _demo(55, 2.0),
    "housing":        _demo(35, 4.0),
    "employment":     _demo(60, 9.0),
    "social_support": _demo(40, 2.5),
}

# ── Weights (must sum to 1.0) ─────────────────────────────────────────────────
WEIGHTS = {
    "healthcare":     0.25,
    "education":      0.20,
    "housing":        0.20,
    "employment":     0.20,
    "social_support": 0.15,
}

# ── Mode ──────────────────────────────────────────────────────────────────────
#   "composite_rate"            → what is the weighted rate of change?
#   "composite_time_to_target"  → when do we hit COMPOSITE_TARGET?
MODE = "composite_time_to_target"

# ── Composite target (only used in "composite_time_to_target" mode) ───────────
COMPOSITE_TARGET = 78.0

# ── Subcategory targets & deadlines ───────────────────────────────────────────
SUB_TARGETS = {
    "healthcare":     80.0,
    "education":      75.0,
    "housing":        75.0,
    "employment":     80.0,
    "social_support": 70.0,
}

SUB_TARGET_TIMES = {
    "healthcare":     timedelta(days=365 * 3),
    "education":      timedelta(days=365 * 3),
    "housing":        timedelta(days=365 * 3),
    "employment":     timedelta(days=365 * 3),
    "social_support": timedelta(days=365 * 3),
}

FORECAST_PERIODS = 365 * 4
PLOT = True

# ═══════════════════════════════════════════════════════════════════════════════
#  RUN — nothing below needs to change
# ═══════════════════════════════════════════════════════════════════════════════

result = simulate_composite_score(
    subcategory_data = SUBCATEGORY_DATA,
    weights          = WEIGHTS,
    mode             = MODE,
    composite_target = COMPOSITE_TARGET,
    sub_targets      = SUB_TARGETS,
    sub_target_times = SUB_TARGET_TIMES,
    forecast_periods = FORECAST_PERIODS,
    plot             = PLOT,
)
