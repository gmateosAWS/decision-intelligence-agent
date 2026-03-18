"""
data/generate_data.py
─────────────────────
Generates a synthetic sales dataset used to train the demand ML model.

All parameters (demand formula coefficients, dataset size, sampling ranges)
are read from the organizational spec (spec/organizational_model.yaml).
To recalibrate the model for a different market context, edit the spec and
re-run this script followed by models/train_demand_model.py.
"""

import sys
from pathlib import Path

# Ensure the project root is on the path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from spec.spec_loader import get_spec


def generate(output_path: str = "data/sales.csv") -> pd.DataFrame:
    spec = get_spec()
    dm = spec.demand_model
    dg = spec.data_generation

    np.random.seed(dg.random_seed)

    price = np.random.uniform(dg.price_min, dg.price_max, dg.n_samples)
    marketing = np.random.uniform(dg.marketing_min, dg.marketing_max, dg.n_samples)

    demand = (
        dm.base_demand
        + dm.price_elasticity * price
        + dm.marketing_effect * marketing
        + np.random.normal(0, dm.noise_sigma, dg.n_samples)
    )

    df = pd.DataFrame({"price": price, "marketing": marketing, "demand": demand})
    df.to_csv(output_path, index=False)

    print(f"Dataset generated: {dg.n_samples} samples -> {output_path}")
    print(
        f"  Formula : demand = {dm.base_demand}"
        f" + ({dm.price_elasticity}) * price"
        f" + {dm.marketing_effect} * marketing"
        f" + noise(sigma={dm.noise_sigma})"
    )
    print(f"  Price   : uniform({dg.price_min}, {dg.price_max})")
    print(f"  Marketing: uniform({dg.marketing_min}, {dg.marketing_max})")
    print(f"  Seed    : {dg.random_seed}")

    return df


if __name__ == "__main__":
    generate()
