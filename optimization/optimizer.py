import numpy as np

from config.settings import (
    get_default_marketing,
    get_price_max,
    get_price_min,
    get_price_steps,
)
from simulation.scenario_runner import run_scenario


def optimize_price(system_model):
    prices = np.linspace(get_price_min(), get_price_max(), get_price_steps())

    results = []

    for p in prices:
        r = run_scenario(system_model, p, get_default_marketing())

        results.append(r)

    best = max(results, key=lambda r: r["expected_profit"])

    # cast a tipos Python nativos
    return {k: float(v) if hasattr(v, "item") else v for k, v in best.items()}
