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
    renames = {}
    for col in df.columns:
        key = re.sub(r"[^a-z0-9]", "", str(col).lower())
        if key in _CANON:
            renames[col] = _CANON[key]
    df = df.rename(columns=renames)

    missing = [c for c in DATA_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Data is missing required columns: {missing}")

    df = df[DATA_COLUMNS].copy()          # drops ids such as _id / id
    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
    if df[TIME_COL].dt.tz is not None:    # keep wall-clock time, as in training
        df[TIME_COL] = df[TIME_COL].dt.tz_localize(None)
    for col in DATA_COLUMNS:
        if col != TIME_COL:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _records(payload) -> list:
    """Pull a list of record dicts out of a typical JSON API response."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "records", "results", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]                  # a single record
    raise ValueError("Unexpected API response format.")


def _get(url: str, params: dict | None = None):
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"API request failed ({url}): {exc}") from exc


def fetch_history_from_api(api_url: str, source: str, as_of=None) -> pd.DataFrame:
    """Latest-record endpoint -> end time; date-range endpoint -> history window."""
    base = api_url.rstrip("/")
    if as_of is None:
        latest = normalise_columns(pd.DataFrame(_records(_get(base + LATEST_PATH.format(source=source)))))
        end = latest[TIME_COL].max()
    else:
        end = pd.Timestamp(as_of)
    start = end - pd.Timedelta(hours=HISTORY_HOURS)

    payload = _get(base + RANGE_PATH.format(source=source),
                   params={START_PARAM: start.isoformat(), END_PARAM: end.isoformat()})
    records = _records(payload)
    if not records:
        raise RuntimeError(f"The API returned no records between {start} and {end}.")
    return normalise_columns(pd.DataFrame(records))


def fetch_history_from_csv(path: Path, as_of=None):
    """Offline alternative: slice the same window out of the CSV.
    Returns (history, actual_next_value_or_None)."""
    df = normalise_columns(pd.read_csv(path))
    df = df.dropna(subset=[TIME_COL]).sort_values(TIME_COL)
    end = pd.Timestamp(as_of) if as_of else df[TIME_COL].max()
    start = end - pd.Timedelta(hours=HISTORY_HOURS)
    history = df[(df[TIME_COL] >= start) & (df[TIME_COL] <= end)]

    actual_rows = df[df[TIME_COL] == end + pd.Timedelta(hours=1)]
    actual = float(actual_rows[TARGET].mean()) if len(actual_rows) else None
    return history, actual


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