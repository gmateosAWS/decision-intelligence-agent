# test_manual.py
from simulation.montecarlo import monte_carlo
from system.system_model import SystemModel

sm = SystemModel()

r25 = monte_carlo(sm, price=25.0, marketing=10000.0)
r49 = monte_carlo(sm, price=48.64, marketing=10000.0)

print(f"€25 → demand={r25['expected_demand']:.1f}  profit={r25['expected_profit']:.2f}")
print(f"€49 → demand={r49['expected_demand']:.1f}  profit={r49['expected_profit']:.2f}")
