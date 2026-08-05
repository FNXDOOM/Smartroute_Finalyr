"""
Train the SmartRouteAI demand prediction model using NYC TLC Yellow Taxi data.

Downloads one month of real trip data (~3M rows), aggregates pickup counts
per H3 zone per hour, engineers the 5 features the backend expects, trains
an XGBoost regressor, and saves the model to ml/models/demand_model.pkl.

Usage:
    python scripts/train_demand_model.py

Requirements (all already in requirements.txt):
    pip install pandas pyarrow xgboost scikit-learn h3 requests
"""
from __future__ import annotations

import os
import sys
import pathlib
import pickle
import requests

# ── Make sure project root is on the path ──────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── Must set SECRET_KEY before importing any backend module ────────────────
os.environ.setdefault("SECRET_KEY", "train-script-placeholder-key")

import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error

# ── Reuse the project's own H3 encoder so features are identical at inference ──
from backend.services.prediction.feature_engineering import encode_h3_index

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# One month of NYC yellow taxi data (~150 MB compressed parquet, ~3M rows).
# Change YEAR/MONTH to use a different month.
YEAR  = 2023
MONTH = 1
DATA_URL = (
    f"https://d37ci6vlwledlt.cloudfront.net/trip-data/"
    f"yellow_tripdata_{YEAR}-{MONTH:02d}.parquet"
)

# H3 resolution — must match the backend (default 9)
H3_RESOLUTION = 9

# Where to cache the downloaded parquet so re-runs are instant
CACHE_DIR  = ROOT / "ml" / "cache"
CACHE_FILE = CACHE_DIR / f"yellow_tripdata_{YEAR}_{MONTH:02d}.parquet"

# Where to save the trained model
MODEL_DIR  = ROOT / "ml" / "models"
MODEL_PATH = MODEL_DIR / "demand_model.pkl"

FEATURE_ORDER = ["hour", "day_of_week", "h3_zone", "historical_count", "is_weekend"]

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Download data (cached)
# ─────────────────────────────────────────────────────────────────────────────

def download_data() -> pathlib.Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists():
        print(f"[cache] Using cached file: {CACHE_FILE}")
        return CACHE_FILE

    print(f"[download] Fetching {DATA_URL} ...")
    response = requests.get(DATA_URL, stream=True, timeout=120)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    with open(CACHE_FILE, "wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            fh.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                print(f"\r  {pct:.1f}%  ({downloaded // 1_048_576} MB / {total // 1_048_576} MB)", end="")
    print(f"\n[download] Saved to {CACHE_FILE}")
    return CACHE_FILE


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Load & clean raw trip data
# ─────────────────────────────────────────────────────────────────────────────

def load_and_clean(parquet_path: pathlib.Path) -> pd.DataFrame:
    print("[load] Reading parquet …")
    df = pd.read_parquet(parquet_path, columns=["tpep_pickup_datetime", "pickup_longitude", "pickup_latitude"])

    print(f"[load] Raw rows: {len(df):,}")

    # Drop rows with missing timestamps or coordinates
    df = df.dropna(subset=["tpep_pickup_datetime", "pickup_longitude", "pickup_latitude"])

    # NYC bounding box — discard obvious bad GPS entries
    df = df[
        (df["pickup_latitude"]  >= 40.4774) & (df["pickup_latitude"]  <= 40.9176) &
        (df["pickup_longitude"] >= -74.2591) & (df["pickup_longitude"] <= -73.7004)
    ]

    df["tpep_pickup_datetime"] = pd.to_datetime(df["tpep_pickup_datetime"], utc=True, errors="coerce")
    df = df.dropna(subset=["tpep_pickup_datetime"])

    print(f"[load] Clean rows: {len(df):,}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Add H3 index column
# ─────────────────────────────────────────────────────────────────────────────

def add_h3_column(df: pd.DataFrame) -> pd.DataFrame:
    print(f"[h3] Computing H3 resolution-{H3_RESOLUTION} indices …")
    try:
        import h3
    except ImportError:
        raise RuntimeError("h3 not installed — run: pip install h3")

    # Vectorised via apply — fast enough for 3M rows in ~30s
    if hasattr(h3, "latlng_to_cell"):
        df["h3_index"] = df.apply(
            lambda row: h3.latlng_to_cell(row["pickup_latitude"], row["pickup_longitude"], H3_RESOLUTION),
            axis=1,
        )
    else:
        df["h3_index"] = df.apply(
            lambda row: h3.geo_to_h3(row["pickup_latitude"], row["pickup_longitude"], H3_RESOLUTION),
            axis=1,
        )
    print(f"[h3] Unique H3 cells: {df['h3_index'].nunique():,}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Aggregate: ride count per (h3_zone, date, hour)
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_demand(df: pd.DataFrame) -> pd.DataFrame:
    print("[agg] Aggregating demand per H3 zone per hour …")

    df["date"]        = df["tpep_pickup_datetime"].dt.date
    df["hour"]        = df["tpep_pickup_datetime"].dt.hour
    df["day_of_week"] = df["tpep_pickup_datetime"].dt.dayofweek   # 0=Mon
    df["is_weekend"]  = (df["day_of_week"] >= 5).astype(int)
    df["h3_zone"]     = df["h3_index"].apply(encode_h3_index)

    agg = (
        df.groupby(["h3_index", "h3_zone", "date", "hour", "day_of_week", "is_weekend"])
        .size()
        .reset_index(name="demand")
    )
    print(f"[agg] Aggregated rows: {len(agg):,}")
    return agg


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Build historical_count feature
# historical_count = average daily demand for this (h3_zone, hour) pair
# This mirrors what the backend computes at inference time
# ─────────────────────────────────────────────────────────────────────────────

def add_historical_count(agg: pd.DataFrame) -> pd.DataFrame:
    print("[feat] Computing historical_count …")
    avg = (
        agg.groupby(["h3_zone", "hour"])["demand"]
        .mean()
        .reset_index()
        .rename(columns={"demand": "historical_count"})
    )
    avg["historical_count"] = avg["historical_count"].round().astype(int)
    agg = agg.merge(avg, on=["h3_zone", "hour"], how="left")
    return agg


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Train XGBoost
# ─────────────────────────────────────────────────────────────────────────────

def train(agg: pd.DataFrame) -> XGBRegressor:
    X = agg[FEATURE_ORDER].values
    y = agg["demand"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )

    print(f"[train] Training on {len(X_train):,} rows, validating on {len(X_test):,} …")

    model = XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        random_state=42,
        n_jobs=-1,               # use all CPU cores
        tree_method="hist",      # fast histogram method
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )

    preds = model.predict(X_test)
    mae  = mean_absolute_error(y_test, preds)
    rmse = mean_squared_error(y_test, preds) ** 0.5
    print(f"\n[eval] MAE  = {mae:.2f} rides")
    print(f"[eval] RMSE = {rmse:.2f} rides")

    # Feature importance
    importance = dict(zip(FEATURE_ORDER, model.feature_importances_))
    print("\n[eval] Feature importances:")
    for feat, score in sorted(importance.items(), key=lambda x: -x[1]):
        bar = "█" * int(score * 40)
        print(f"  {feat:<20} {score:.4f}  {bar}")

    return model


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Save model
# ─────────────────────────────────────────────────────────────────────────────

def save_model(model: XGBRegressor) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as fh:
        pickle.dump(model, fh)
    size_kb = MODEL_PATH.stat().st_size // 1024
    print(f"\n[save] Model saved → {MODEL_PATH}  ({size_kb} KB)")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  SmartRouteAI — Demand Model Training")
    print(f"  Dataset : NYC Yellow Taxi {YEAR}-{MONTH:02d}")
    print(f"  H3 res  : {H3_RESOLUTION}")
    print("=" * 60)

    parquet_path = download_data()
    df           = load_and_clean(parquet_path)
    df           = add_h3_column(df)
    agg          = aggregate_demand(df)
    agg          = add_historical_count(agg)
    model        = train(agg)
    save_model(model)

    print("\n✓ Done. Backend will now use XGBoost instead of the heuristic fallback.")
    print("  Restart the server to reload the model (or it auto-loads on first request).")


if __name__ == "__main__":
    main()
