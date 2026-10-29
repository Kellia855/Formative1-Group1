"""
Shared preprocessing for the electricity-consumption forecaster.

These functions are copied unchanged from the Task 1 notebook (Sections 17.2
and 17.3) so that training (Task 1) and prediction (Task 4) use exactly the
same pipeline. Import them from here in BOTH places; never re-type them.
"""
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- constants
TARGET = "Consumption"
TIME_COL = "DateTime"
FREQ = "h"                      # hourly data
MAX_GAP_HOURS = 6               # longest gap we are willing to interpolate
LAGS = [1, 2, 3, 24, 48, 168]   # 1-3 hours, 1 day, 2 days, 1 week
ROLL_WINDOWS = [24, 168]        # 1 day, 1 week
DATA_COLUMNS = [TIME_COL, TARGET, "Production", "Nuclear", "Wind",
                "Hydroelectric", "Oil and Gas", "Coal", "Solar", "Biomass"]
MIN_HISTORY_HOURS = max(LAGS + ROLL_WINDOWS)   # 168 hours of past data needed


# ------------------------------------------------------------------ cleaning
def _fill_short_gaps(df, max_gap_hours):
    """Interpolate only gaps that are <= max_gap_hours long IN FULL.
    (pandas' limit= would half-fill longer gaps, which we do not want.)"""
    filled = df.interpolate(method="time", limit_area="inside")
    for col in df.columns:
        na = df[col].isna()
        run_id = (~na).cumsum()                         # label each run of consecutive NaNs
        run_len = na.groupby(run_id).transform("sum")
        filled.loc[na & (run_len > max_gap_hours), col] = np.nan
    return filled


def clean_data(df_raw, freq=FREQ, max_gap_hours=MAX_GAP_HOURS):
    """Return a cleaned hourly DataFrame indexed by DateTime and a report dict."""
    report = {"rows_raw": int(len(df_raw))}
    df = df_raw.copy()
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]  # stray index columns

    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
    report["invalid_timestamps_dropped"] = int(df[TIME_COL].isna().sum())
    df = df.dropna(subset=[TIME_COL]).sort_values(TIME_COL)

    report["exact_duplicates_dropped"] = int(df.duplicated().sum())
    df = df.drop_duplicates()

    num_cols = df.select_dtypes("number").columns.tolist()
    report["repeated_timestamps_collapsed"] = int(df[TIME_COL].duplicated().sum())
    df = df.groupby(TIME_COL)[num_cols].mean()

    gen_cols = [c for c in num_cols if c != TARGET]
    neg = (df[gen_cols] < 0).sum()
    report["negative_values_clipped"] = {c: int(n) for c, n in neg.items() if n}
    df[gen_cols] = df[gen_cols].clip(lower=0)

    full_index = pd.date_range(df.index.min(), df.index.max(), freq=freq, name=TIME_COL)
    report["off_grid_timestamps_dropped"] = int(len(df.index.difference(full_index)))
    report["missing_timestamps_inserted"] = int(len(full_index.difference(df.index)))
    df = df.reindex(full_index)

    report["nan_before_fill"] = {c: int(n) for c, n in df.isna().sum().items() if n}
    df = _fill_short_gaps(df, max_gap_hours)
    report["nan_after_fill"] = {c: int(n) for c, n in df.isna().sum().items() if n}

    report.update(rows_clean=int(len(df)), start=str(df.index.min()), end=str(df.index.max()))
    return df, report


# --------------------------------------------------------- feature engineering
def add_features(df, drop_na=True):
    """Build model features from the cleaned hourly DataFrame (leakage-safe)."""
    out = pd.DataFrame(index=df.index)
    out[TARGET] = df[TARGET]

    for lag in LAGS:
        out[f"{TARGET}_lag_{lag}"] = df[TARGET].shift(lag)

    past = df[TARGET].shift(1)           # exclude the current value from windows
    for w in ROLL_WINDOWS:
        out[f"{TARGET}_ma_{w}"] = past.rolling(w, min_periods=w).mean()
        out[f"{TARGET}_std_{w}"] = past.rolling(w, min_periods=w).std()

    for c in [c for c in df.columns if c != TARGET]:
        out[f"{c}_lag_1"] = df[c].shift(1)

    idx = df.index
    out["hour"] = idx.hour
    out["dayofweek"] = idx.dayofweek
    out["month"] = idx.month
    out["is_weekend"] = (idx.dayofweek >= 5).astype(int)
    out["hour_sin"] = np.sin(2 * np.pi * idx.hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * idx.hour / 24)
    out["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7)
    out["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7)
    out["month_sin"] = np.sin(2 * np.pi * (idx.month - 1) / 12)
    out["month_cos"] = np.cos(2 * np.pi * (idx.month - 1) / 12)

    return out.dropna() if drop_na else out


# ------------------------------------------------- serving-time (Task 4 only)
def build_next_hour_features(raw_history, feature_columns):
    """Clean a window of recent raw records and build the feature row for the
    NEXT hour (the one we want to forecast).

    The next hour does not exist yet, so an empty placeholder row is appended.
    add_features only reads past values (shift / rolling on shifted data) and
    the timestamp itself, so every feature of that row comes from real history.

    Returns (next_timestamp, one_row_dataframe_in_training_column_order, report).
    """
    clean, report = clean_data(raw_history)
    if len(clean) < MIN_HISTORY_HOURS:
        raise ValueError(
            f"Need at least {MIN_HISTORY_HOURS} hourly records to build lag/rolling "
            f"features, but only {len(clean)} are available after cleaning.")

    next_ts = clean.index.max() + pd.Timedelta(hours=1)
    placeholder = pd.DataFrame(np.nan, index=pd.DatetimeIndex([next_ts], name=TIME_COL),
                               columns=clean.columns)
    feats = add_features(pd.concat([clean, placeholder]), drop_na=False)

    row = feats.loc[[next_ts], list(feature_columns)]
    if row.isna().any(axis=None):
        bad = row.columns[row.isna().any()].tolist()
        raise ValueError(
            f"Could not build features for {next_ts}: missing {bad}. The recent history "
            "probably contains a gap longer than 6 hours.")
    return next_ts, row, report