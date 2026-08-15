"""
Train the SmartRouteAI demand model using SYNTHETIC data.

Use this if you can't download the NYC TLC dataset or want a fast offline demo.
Generates statistically realistic demand patterns:
  - Morning rush (7–9am) and evening rush (5–7pm) peaks
  - Weekend ~20% lower demand
  - Spatial hotspots (city centre > suburbs)
  - Random noise

Produces the same ml/models/demand_model.pkl the backend expects.

Usage:
    python scripts/train_demand_model_synthetic.py
"""
from __future__ import annotations

import os
import sys
import pickle
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

from backend.services.prediction.feature_engineering import encode_h3_index
from backend.services.clustering.h3_partitioner import get_h3_index

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — adjust city centre and spread to match your deployment city
# ─────────────────────────────────────────────────────────────────────────────

# Dubai (matches the seed_db.py default)
CITY_CENTER    = (25.2048, 55.2708)
SPREAD_DEGREES = 0.15          # ~15 km radius
N_DAYS         = 180           # 6 months of synthetic history
N_ZONES        = 40            # number of synthetic H3 hotspot zones
H3_RESOLUTION  = 9

MODEL_PATH = ROOT / "ml" / "models" / "demand_model.pkl"
FEATURE_ORDER = ["hour", "day_of_week", "h3_zone", "historical_count", "is_weekend"]

rng = np.random.default_rng(42)


# ─────────────────────────────────────────────────────────────────────────────
# DEMAND SHAPE — mirrors real urban ride-hailing patterns
# ─────────────────────────────────────────────────────────────────────────────

HOUR_MULTIPLIERS = {
    0: 0.3, 1: 0.2, 2: 0.15, 3: 0.1, 4: 0.1, 5: 0.2,
    6: 0.5, 7: 1.4, 8: 1.8, 9: 1.3, 10: 0.9, 11: 0.85,
    12: 1.0, 13: 0.95, 14: 0.9, 15: 0.95, 16: 1.1,
    17: 1.7, 18: 1.9, 19: 1.5, 20: 1.1, 21: 0.9,
    22: 0.7, 23: 0.5,
}

DOW_MULTIPLIERS = {
    0: 1.0,   # Monday
    1: 1.05,
    2: 1.05,
    3: 1.1,
    4: 1.2,   # Friday
    5: 0.85,  # Saturday
    6: 0.75,  # Sunday
}


def _make_zone_centers(n: int) -> list[tuple[float, float, float]]:
    """Return (lat, lng, base_demand) for N synthetic hotspot zones."""
    zones = []
    for _ in range(n):
        # Distance from centre: closer zones = higher base demand
        radius = rng.uniform(0, SPREAD_DEGREES)
        angle  = rng.uniform(0, 2 * 3.14159)
        lat    = CITY_CENTER[0] + radius * float(np.cos(angle))
        lng    = CITY_CENTER[1] + radius * float(np.sin(angle))
        # Base demand decays with distance from centre
        base   = max(2.0, 30.0 * (1 - radius / SPREAD_DEGREES) + rng.uniform(1, 10))
        zones.append((lat, lng, base))
    return zones


def generate_dataset() -> pd.DataFrame:
    print(f"[synth] Generating {N_DAYS} days × {N_ZONES} zones × 24 hours …")

    zone_centers = _make_zone_centers(N_ZONES)

    # Pre-compute H3 index and encoded zone for each synthetic zone
    zone_h3 = [
        get_h3_index(lat, lng, H3_RESOLUTION)
        for lat, lng, _ in zone_centers
    ]
    zone_encoded = [encode_h3_index(h) for h in zone_h3]

    rows = []
    for day_offset in range(N_DAYS):
        dow        = day_offset % 7
        is_weekend = 1 if dow >= 5 else 0
        dow_mult   = DOW_MULTIPLIERS[dow]

        for hour in range(24):
            hour_mult = HOUR_MULTIPLIERS[hour]

            for zone_idx, (_, _, base_demand) in enumerate(zone_centers):
                # Expected demand for this zone/hour/day
                expected = base_demand * hour_mult * dow_mult
                # Add Poisson noise — realistic for count data
                actual = int(rng.poisson(max(0.1, expected)))

                rows.append({
                    "hour":             hour,
                    "day_of_week":      dow,
                    "h3_zone":          zone_encoded[zone_idx],
                    "is_weekend":       is_weekend,
                    "demand":           actual,
                    # historical_count filled in next step
                })

    df = pd.DataFrame(rows)
    print(f"[synth] Generated {len(df):,} rows")
    return df


def add_historical_count(df: pd.DataFrame) -> pd.DataFrame:
    """historical_count = mean demand for (h3_zone, hour) across all days."""
    avg = (
        df.groupby(["h3_zone", "hour"])["demand"]
        .mean()
        .reset_index()
        .rename(columns={"demand": "historical_count"})
    )
    avg["historical_count"] = avg["historical_count"].round().astype(int)
    return df.merge(avg, on=["h3_zone", "hour"], how="left")


def train(df: pd.DataFrame) -> XGBRegressor:
    X = df[FEATURE_ORDER].values
    y = df["demand"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )
    print(f"[train] Training on {len(X_train):,} rows …")

    model = XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        random_state=42,
        n_jobs=-1,
        tree_method="hist",
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=50)

    preds = model.predict(X_test)
    mae   = mean_absolute_error(y_test, preds)
    print(f"\n[eval] MAE = {mae:.2f} rides per zone-hour")

    importance = dict(zip(FEATURE_ORDER, model.feature_importances_))
    print("\n[eval] Feature importances:")
    for feat, score in sorted(importance.items(), key=lambda x: -x[1]):
        bar = "█" * int(score * 40)
        print(f"  {feat:<20} {score:.4f}  {bar}")

    return model


def main():
    print("=" * 60)
    print("  SmartRouteAI — Demand Model Training (Synthetic)")
    print(f"  City   : {CITY_CENTER}")
    print(f"  Days   : {N_DAYS}  |  Zones : {N_ZONES}  |  H3 res : {H3_RESOLUTION}")
    print("=" * 60)

    df    = generate_dataset()
    df    = add_historical_count(df)
    model = train(df)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as fh:
        pickle.dump(model, fh)

    size_kb = MODEL_PATH.stat().st_size // 1024
    print(f"\n[save] Model saved → {MODEL_PATH}  ({size_kb} KB)")
    print("\n✓ Done. Backend will now use XGBoost instead of the heuristic fallback.")


if __name__ == "__main__":
    main()
