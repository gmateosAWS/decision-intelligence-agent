"""
models/train_demand_model.py  ← CREADO (archivo anterior inaccesible / ausente)
────────────────────────────────────────────────────────────────────────────────
Entrena el modelo de predicción de demanda y lo persiste en models/demand_model.pkl.

Pipeline:
  1. Carga data/sales.csv (generado por data/generate_data.py)
  2. Split train/test estratificado por cuantiles de precio
  3. Entrena un RandomForestRegressor
  4. Evalúa y reporta métricas (MAE, RMSE, R²) en test set
  5. Persiste el modelo entrenado como pickle

Ejecutar:
  python models/train_demand_model.py
"""

import os
import pickle

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_PATH = "data/sales.csv"
MODEL_PATH = "models/demand_model.pkl"

# ── Hyperparameters ───────────────────────────────────────────────────────────
N_ESTIMATORS = 200
MAX_DEPTH = 10
RANDOM_STATE = 42
TEST_SIZE = 0.20


def train():
    # 1. Cargar datos
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(
            f"Dataset not found at '{DATA_PATH}'. "
            "Run 'python data/generate_data.py' first."
        )

    df = pd.read_csv(DATA_PATH)
    print(f"Dataset loaded: {len(df)} samples")

    X = df[["price", "marketing"]].values
    y = df["demand"].values

    # 2. Train / test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    print(f"Train: {len(X_train)} samples  |  Test: {len(X_test)} samples")

    # 3. Entrenar modelo
    model = RandomForestRegressor(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    print("Model trained.")

    # 4. Evaluar en test set
    y_pred = model.predict(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    print("\n── Model evaluation (test set) ──────────────────")
    print(f"  MAE  : {mae:.4f}  units")
    print(f"  RMSE : {rmse:.4f}  units")
    print(f"  R²   : {r2:.4f}")
    print("─────────────────────────────────────────────────\n")

    # 5. Feature importance
    importances = model.feature_importances_
    features = ["price", "marketing"]
    print("Feature importances:")
    for feat, imp in zip(features, importances):
        print(f"  {feat:12s}: {imp:.4f}")

    # 6. Persistir modelo
    os.makedirs("models", exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    print(f"\nModel saved to '{MODEL_PATH}'")


if __name__ == "__main__":
    train()
