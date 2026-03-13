from simulation.montecarlo import monte_carlo

def run_scenario(system_model, price, marketing):

    result = monte_carlo(system_model, price, marketing)

    result["price"] = price
    result["marketing"] = marketing

    return result