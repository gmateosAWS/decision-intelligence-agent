"""
data/generate_data.py
─────────────────────
Generates a synthetic sales dataset used to train the demand ML model.

Two generation modes are controlled by spec.data_generation.temporal:

  temporal=False (legacy)
    Flat random sample over price × marketing space; linear demand formula.
    Produces: price, marketing, demand

  temporal=True
    36 months of monthly observations with seasonality, growth trend,
    log-marketing effect and quadratic price elasticity.
    Produces: price, marketing, demand, month

All parameters (coefficients, size, ranges) are read from the spec so that
recalibrating the model requires only editing organizational_model.yaml and
re-running this script followed by models/train_demand_model.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from spec.spec_loader import get_spec


def _generate_flat(spec, rng: np.random.Generator) -> pd.DataFrame:
    """Legacy flat generator — linear demand formula, no month column."""
    dm = spec.demand_model
    dg = spec.data_generation

    price = rng.uniform(dg.price_min, dg.price_max, dg.n_samples)
    marketing = rng.uniform(dg.marketing_min, dg.marketing_max, dg.n_samples)

    demand = (
        dm.base_demand
        + dm.price_elasticity * price
        + dm.marketing_effect * marketing
        + rng.normal(0, dm.noise_sigma, dg.n_samples)
    )

    print(
        f"  Mode    : flat (temporal=false)\n"
        f"  Formula : demand = {dm.base_demand}"
        f" + ({dm.price_elasticity}) * price"
        f" + {dm.marketing_effect} * marketing"
        f" + noise(sigma={dm.noise_sigma})"
    )
    return pd.DataFrame({"price": price, "marketing": marketing, "demand": demand})


def _generate_temporal(spec, rng: np.random.Generator) -> pd.DataFrame:
    """Temporal generator with seasonality, trend, log-marketing, quadratic price."""
    dm = spec.demand_model
    dg = spec.data_generation

    n_months = dg.n_months
    samples_per_month = max(1, dg.n_samples // n_months)

    rows = []
    for month in range(1, n_months + 1):
        n = samples_per_month
        price = rng.uniform(dg.price_min, dg.price_max, n)
        marketing = rng.uniform(dg.marketing_min, dg.marketing_max, n)

        seasonal = dg.seasonality_amplitude * np.sin(2 * np.pi * month / 12)
        trend = dg.trend_slope * month

        demand = (
            dm.base_demand
            + dm.price_elasticity * price
            + dm.price_quadratic * price**2
            + dm.marketing_effect * np.log(marketing)
            + seasonal
            + trend
            + rng.normal(0, dm.noise_sigma, n)
        )

        rows.append(
            pd.DataFrame(
                {
                    "price": price,
                    "marketing": marketing,
                    "demand": demand,
                    "month": month,
                }
            )
        )

    total = samples_per_month * n_months
    print(
        f"  Mode    : temporal (n_months={n_months}, {samples_per_month} obs/month)\n"
        f"  Formula : demand = {dm.base_demand}"
        f" + ({dm.price_elasticity})*price"
        f" + {dm.price_quadratic}*price²"
        f" + {dm.marketing_effect}*log(marketing)"
        f" + {dg.seasonality_amplitude}*sin(2*pi*month/12)"
        f" + {dg.trend_slope}*month"
        f" + noise(sigma={dm.noise_sigma})\n"
        f"  Total rows: {total}"
    )
    return pd.concat(rows, ignore_index=True)


def generate(output_path: str = "data/sales.csv") -> pd.DataFrame:
    spec = get_spec()
    dg = spec.data_generation

    rng = np.random.default_rng(dg.random_seed)

    print(f"Generating dataset -> {output_path}")
    print(f"  Price   : uniform({dg.price_min}, {dg.price_max})")
    print(f"  Marketing: uniform({dg.marketing_min}, {dg.marketing_max})")
    print(f"  Seed    : {dg.random_seed}")

    if dg.temporal:
        df = _generate_temporal(spec, rng)
    else:
        df = _generate_flat(spec, rng)

    df.to_csv(output_path, index=False)
    print(f"Dataset saved: {len(df)} rows -> {output_path}")
    return df


if __name__ == "__main__":
    generate()
