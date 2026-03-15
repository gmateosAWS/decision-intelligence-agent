from simulation.montecarlo import monte_carlo


def run_scenario(system_model, price, marketing):
    return monte_carlo(system_model, price, marketing)
