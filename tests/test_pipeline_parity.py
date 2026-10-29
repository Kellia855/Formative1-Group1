"""
Training/serving parity test.

The Task 4 script builds the feature row for the next hour from a short window
of history. This test checks that row is IDENTICAL to the row the Task 1
pipeline computes for the same timestamp on the full dataset. If it fails, the
model would be fed different inputs at prediction time than it saw in training.

Run:  python -m pytest tests/   (or)   python tests/test_pipeline_parity.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.preprocessing import DATA_COLUMNS, TIME_COL, add_features, build_next_hour_features, clean_data


def make_synthetic(hours=800, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=hours, freq="h")
    base = 6000 + 1500 * np.sin(2 * np.pi * (idx.hour - 6) / 24) + rng.normal(0, 80, hours)
    df = pd.DataFrame({TIME_COL: idx, "Consumption": base})
    for c in DATA_COLUMNS[2:]:
        df[c] = rng.uniform(0, 2000, hours)
    return df


def test_next_hour_row_matches_training_pipeline():
    raw = make_synthetic()
    full_clean, _ = clean_data(raw)
    full_feats = add_features(full_clean, drop_na=False)
    feature_cols = [c for c in full_feats.columns if c != "Consumption"]

    target_ts = full_clean.index[500]
    window = raw[(raw[TIME_COL] >= target_ts - pd.Timedelta(hours=192)) &
                 (raw[TIME_COL] < target_ts)]          # history strictly BEFORE the target hour

    ts, row, _ = build_next_hour_features(window, feature_cols)
    assert ts == target_ts
    np.testing.assert_allclose(row.iloc[0].to_numpy(float),
                               full_feats.loc[target_ts, feature_cols].to_numpy(float))


def test_too_little_history_is_rejected():
    raw = make_synthetic(hours=50)
    try:
        build_next_hour_features(raw, ["Consumption_lag_1"])
    except ValueError:
        return
    raise AssertionError("expected ValueError for short history")


if __name__ == "__main__":
    test_next_hour_row_matches_training_pipeline()
    test_too_little_history_is_rejected()
    print("All parity tests passed.")