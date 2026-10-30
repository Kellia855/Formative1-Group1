"""
Task 4: forecast the next hour of electricity consumption.

Workflow
    1. Fetch recent hourly records from the API (latest record + date range)
    2. Preprocess them with the SAME pipeline as Task 1 (src/preprocessing.py)
    3. Load the trained model saved by the Task 1 notebook
    4. Predict Consumption for the next hour

Examples (run from the repository root)
    python predict_forecast.py --api http://localhost:8000 --source sql
    python predict_forecast.py --api http://localhost:8000 --source mongo
    python predict_forecast.py --api http://localhost:8000 --as-of "2024-03-31 12:00"

    # Offline demo / back-test straight from the CSV (no API needed). It also
    # prints the actual value when the hour being forecast is in the file:
    python predict_forecast.py --csv data/Electricity.csv --as-of "2024-03-31 22:00"

Adjust LATEST_PATH / RANGE_PATH / the query parameter names below so they match
your Task 3 endpoints.
"""
import argparse
import re
import sys
from pathlib import Path

import joblib
import pandas as pd
import requests

from src.preprocessing import (DATA_COLUMNS, TARGET, TIME_COL,
                               build_next_hour_features)

# ----------------------------------------------------------------- settings
DEFAULT_MODEL = Path("models/best_model.joblib")
HISTORY_HOURS = 192                      # 168 h needed + a small buffer for gaps
LATEST_PATH = "/{source}/records/latest"
RANGE_PATH = "/{source}/records/range"    # called with ?start=...&end=...
START_PARAM, END_PARAM = "start", "end"

# Accept "oil_and_gas", "Oil and Gas", "oilAndGas", "timestamp" ... from the API
_CANON = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in DATA_COLUMNS}
_CANON.update({"timestamp": TIME_COL, "date": TIME_COL, "time": TIME_COL})


# ------------------------------------------------------------ data loading
def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map API/CSV column names onto the names used during training."""

    df = df.copy()

    # Expand nested generation values returned by the SQL/Mongo API
    if "generation" in df.columns:
        generation = pd.json_normalize(df["generation"].tolist())
        generation.index = df.index
        df = pd.concat(
            [df.drop(columns=["generation"]), generation],
            axis=1
        )

    # Normalize column names
    renames = {}

    for col in df.columns:
        key = re.sub(r"[^a-z0-9]", "", str(col).lower())

        if key in _CANON:
            renames[col] = _CANON[key]

    df = df.rename(columns=renames)

    # Check that all required columns exist
    missing = [c for c in DATA_COLUMNS if c not in df.columns]

    if missing:
        raise ValueError(
            f"Data is missing required columns: {missing}"
        )

    # Keep only the columns used during training
    df = df[DATA_COLUMNS].copy()

    # Convert timestamps
    df[TIME_COL] = pd.to_datetime(
        df[TIME_COL],
        errors="coerce"
    )

    if df[TIME_COL].dt.tz is not None:
        df[TIME_COL] = df[TIME_COL].dt.tz_localize(None)

    # Convert numerical columns
    for col in DATA_COLUMNS:
        if col != TIME_COL:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

    return df
# -------------------------------------------------------------- forecasting
def load_model(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Model not found at {path}. Run the Task 1 notebook and copy "
            "best_model.joblib into the models/ folder.")
    bundle = joblib.load(path)
    for key in ("model", "features"):
        if key not in bundle:
            raise KeyError(f"Model file is missing '{key}'.")
    return bundle


def forecast_next_hour(raw_history: pd.DataFrame, bundle: dict):
    """Preprocess -> build features -> predict. Returns (timestamp, value, last_observed)."""
    next_ts, row, report = build_next_hour_features(raw_history, bundle["features"])
    prediction = float(bundle["model"].predict(row)[0])
    last_observed = float(row["Consumption_lag_1"].iloc[0])
    return next_ts, prediction, last_observed, report


# --------------------------------------------------------------------- main
def parse_args():
    p = argparse.ArgumentParser(description="Forecast next-hour electricity consumption.")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--api", default="http://localhost:8000", help="base URL of the API (default)")
    src.add_argument("--csv", type=Path, help="read history from a CSV instead of the API")
    p.add_argument("--source", choices=["sql", "mongo"], default="sql",
                   help="which database the API should read from")
    p.add_argument("--as-of", help="forecast the hour AFTER this timestamp (default: latest record)")
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        bundle = load_model(args.model)
        actual = None
        if args.csv:
            print(f"[1/4] Reading history from {args.csv}")
            history, actual = fetch_history_from_csv(args.csv, args.as_of)
        else:
            print(f"[1/4] Fetching history from {args.api} ({args.source})")
            history = fetch_history_from_api(args.api, args.source, args.as_of)
        print(f"      {len(history)} raw records, {history[TIME_COL].min()} -> {history[TIME_COL].max()}")

        print("[2/4] Preprocessing (same pipeline as Task 1)")
        print("[3/4] Model loaded:", type(bundle["model"]).__name__)
        ts, pred, last, report = forecast_next_hour(history, bundle)
        print(f"      cleaning report: {report['exact_duplicates_dropped']} duplicates, "
              f"{report['repeated_timestamps_collapsed']} repeated timestamps, "
              f"{report['missing_timestamps_inserted']} missing hours inserted")
    except (RuntimeError, ValueError, FileNotFoundError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("[4/4] Forecast")
    print(f"      Hour forecast      : {ts}")
    print(f"      Last observed      : {last:,.0f}")
    print(f"      Predicted {TARGET}: {pred:,.1f}")
    if actual is not None:
        print(f"      Actual (back-test) : {actual:,.1f}   |   absolute error: {abs(actual - pred):,.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())