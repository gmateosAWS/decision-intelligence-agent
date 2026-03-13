import numpy as np
from simulation.scenario_runner import run_scenario
from config.settings import *

def optimize_price(system_model):

    prices = np.linspace(PRICE_MIN, PRICE_MAX, PRICE_STEPS)

    results = []

    for p in prices:

        r = run_scenario(system_model, p, DEFAULT_MARKETING)

        results.append(r)

    best = max(results, key=lambda x: x["expected_profit"])

    return best