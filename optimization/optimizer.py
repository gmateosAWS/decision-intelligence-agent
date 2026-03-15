import numpy as np

from config.settings import DEFAULT_MARKETING, PRICE_MAX, PRICE_MIN, PRICE_STEPS
from simulation.scenario_runner import run_scenario


def optimize_price(system_model):
    prices = np.linspace(PRICE_MIN, PRICE_MAX, PRICE_STEPS)

    results = []

    for p in prices:
        r = run_scenario(system_model, p, DEFAULT_MARKETING)

        results.append(r)

    best = max(results, key=lambda r: r["expected_profit"])

    # cast a tipos Python nativos
    return {k: float(v) if hasattr(v, "item") else v for k, v in best.items()}
