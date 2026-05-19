import xgboost as xgb
import numpy as np
import pickle
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "../../../ml/models/demand_model.pkl")


def load_model():
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict_demand(features: dict) -> float:
    """
    Predict ride demand for a given zone and time.
    features: dict with keys like hour, day_of_week, h3_index_encoded, etc.
    Returns predicted demand count (float).
    """
    model = load_model()
    X = np.array([[
        features.get("hour", 0),
        features.get("day_of_week", 0),
        features.get("h3_zone", 0),
        features.get("is_weekend", 0),
    ]])
    prediction = model.predict(X)
    return float(prediction[0])
