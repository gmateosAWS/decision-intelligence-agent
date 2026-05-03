"""
models/train_demand_model.py
────────────────────────────
Trains the demand prediction model and persists it to models/demand_model.pkl.

Pipeline:
  1. Load data/sales.csv (produced by data/generate_data.py)
  2. Auto-detect feature set: [price, marketing] or [price, marketing, month]
  3. Train/test split (stratified by price quantiles)
  4. Train a RandomForestRegressor
  5. Evaluate on the test set (MAE, RMSE, R²) and print feature importances
  6. Persist the trained model as pickle

Run:
  python models/train_demand_model.py
"""

import os
import pickle

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

DATA_PATH = "data/sales.csv"
MODEL_PATH = "models/demand_model.pkl"

N_ESTIMATORS = 200
MAX_DEPTH = 10
RANDOM_STATE = 42
TEST_SIZE = 0.20


def train():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(
            f"Dataset not found at '{DATA_PATH}'. "
            "Run 'python data/generate_data.py' first."
        )

    df = pd.read_csv(DATA_PATH)
    print(f"Dataset loaded: {len(df)} rows")

    # Auto-detect feature set
    base_features = ["price", "marketing"]
    features = base_features + (["month"] if "month" in df.columns else [])
    print(f"Features      : {features}")

    X = df[features].values
    y = df["demand"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    print(f"Train: {len(X_train)} samples  |  Test: {len(X_test)} samples")

    model = RandomForestRegressor(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    print("Model trained.")

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    print("\n--- Model evaluation (test set) -----------------")
    print(f"  MAE  : {mae:.4f}  units")
    print(f"  RMSE : {rmse:.4f}  units")
    print(f"  R2   : {r2:.4f}")
    print("-------------------------------------------------\n")

    print("Feature importances:")
    for feat, imp in zip(features, model.feature_importances_):
        print(f"  {feat:12s}: {imp:.4f}  ({imp * 100:.1f}%)")

    os.makedirs("models", exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    print(f"\nModel saved to '{MODEL_PATH}'")


if __name__ == "__main__":
    train()
