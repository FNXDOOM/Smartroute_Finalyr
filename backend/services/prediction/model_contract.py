"""The demand model's train/serve contract.

Where the artifact lives and the feature order it was trained on. The training
script and the serving path both import these, so the two cannot drift apart —
which would silently feed the model its features in the wrong order.

Deliberately dependency-free: the training script imports it without pulling in
the ORM or the request models.
"""

from pathlib import Path

# backend/services/prediction/model_contract.py -> repo root is parents[3].
MODEL_PATH = Path(__file__).resolve().parents[3] / "ml" / "models" / "demand_model.pkl"

FEATURE_ORDER = ["hour", "day_of_week", "h3_zone", "historical_count", "is_weekend"]
