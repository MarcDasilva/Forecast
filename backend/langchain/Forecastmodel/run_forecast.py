"""
run_forecast.py — configure and run forecast_score in one place.

Edit the CONFIG section below, then run:
    python3 run_forecast.py
"""

import warnings
warnings.filterwarnings("ignore")
import logging
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

import pandas as pd
from datetime import timedelta
from forecast_score import forecast_score

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG — the only section you need to edit
# ═══════════════════════════════════════════════════════════════════════════════

CSV_PATH = "data/samples/Fake_Data_better2.csv"
DS_COL   = "Date"           # column containing dates / periods
Y_COL    = "Score"   # column containing the score to forecast

MODE     = "required_rate"   # "time_to_target"  or  "required_rate"

TARGET_Y    = 90.0              # score you want to reach
TARGET_TIME = timedelta(days=37) # deadline — days from last data point,
                                 #   OR an ISO string like "2026-06-30"
                                 #   (only used in "required_rate" mode)

FORECAST_PERIODS = 730   # how many days ahead Prophet should look
PLOT             = True

# ═══════════════════════════════════════════════════════════════════════════════
#  RUN — nothing below needs to change
# ═══════════════════════════════════════════════════════════════════════════════

# ── Load & preview ────────────────────────────────────────────────────────────
raw = pd.read_csv(CSV_PATH)

# Show available columns so it's easy to choose DS_COL / Y_COL
print("Available columns:", list(raw.columns))
print(f"Using  ds='{DS_COL}'  y='{Y_COL}'")
print(f"Unique dates in '{DS_COL}': {raw[DS_COL].nunique()}  "
      f"(total rows: {len(raw)})")
print()

df = raw.rename(columns={DS_COL: "ds", Y_COL: "y"})

result = forecast_score(
    data_input       = df,
    mode             = MODE,
    target_y         = TARGET_Y,
    target_time      = TARGET_TIME,
    forecast_periods = FORECAST_PERIODS,
    plot             = PLOT,
    plot_title       = f"{Y_COL} — {MODE.replace('_', ' ').title()}",
)

print()
print("── Result ──────────────────────────────────────────────")
for key, val in result.items():
    if key == "forecast_df":
        continue
    print(f"  {key:<28} {round(val, 4) if isinstance(val, float) else val}")
