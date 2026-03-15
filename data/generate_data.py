import numpy as np
import pandas as pd

np.random.seed(42)

n = 2000

price = np.random.uniform(10, 50, n)
marketing = np.random.uniform(1_000, 20_000, n)  # en € reales

base_demand = 120
price_effect = -1.6 * price
marketing_effect = 0.0009 * marketing  # ← ajustado

noise = np.random.normal(0, 5, n)
demand = base_demand + price_effect + marketing_effect + noise

df = pd.DataFrame({"price": price, "marketing": marketing, "demand": demand})
df.to_csv("data/sales.csv", index=False)
print("Dataset generated")
