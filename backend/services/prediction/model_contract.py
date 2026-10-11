"""Train/serve contract for the demand model: artifact path and feature order, dependency-free so training can import it without the ORM."""

from pathlib import Path

# backend/services/prediction/model_contract.py -> repo root is parents[3].
MODEL_PATH = Path(__file__).resolve().parents[3] / "ml" / "models" / "demand_model.pkl"

FEATURE_ORDER = ["hour", "day_of_week", "h3_zone", "historical_count", "is_weekend"]
