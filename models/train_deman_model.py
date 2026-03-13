import pickle

import pandas as pd
from sklearn.ensemble import RandomForestRegressor

df = pd.read_csv("data/sales.csv")

X = df[["price", "marketing"]]
y = df["demand"]

model = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)

model.fit(X, y)

pickle.dump(model, open("models/demand_model.pkl", "wb"))

print("Demand model trained")
