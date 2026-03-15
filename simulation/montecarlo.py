"""
simulation/montecarlo.py  ← REESCRITO (archivo anterior tenía contenido incorrecto)
─────────────────────────────────────────────────────────────────────────────
Implementa la simulación Monte Carlo para evaluar decisiones bajo incertidumbre.

El enfoque es:
  - Para un par (price, marketing) dado, ejecutar N evaluaciones del modelo.
  - En cada run, añadir ruido gaussiano a la predicción de demanda para capturar
    la incertidumbre del modelo ML y la variabilidad del mercado.
  - Devolver distribución estadística del beneficio esperado.

Este módulo NO contiene lógica de negocio. Recibe un system_model ya instanciado
y delega toda la evaluación causal en él.
"""

import numpy as np

from config.settings import MC_RUNS


def monte_carlo(
    system_model, price: float, marketing: float, n_runs: int = None
) -> dict:
    """
    Ejecuta una simulación Monte Carlo para estimar la distribución de beneficio
    bajo incertidumbre de demanda.

    Args:
        system_model: Instancia de SystemModel. Proporciona evaluate() y unit_cost.
        price:        Precio unitario del producto.
        marketing:    Inversión en marketing del período.
        n_runs:       Número de simulaciones. Si None, usa MC_RUNS de config.

    Returns:
        Dict con estadísticas de la distribución de resultados:
          - expected_profit   : media del beneficio
          - profit_std        : desviación estándar del beneficio
          - profit_p10        : percentil 10 (escenario pesimista)
          - profit_p90        : percentil 90 (escenario optimista)
          - expected_demand   : media de la demanda estimada
          - demand_std        : desviación estándar de la demanda
          - n_runs            : número de simulaciones ejecutadas
          - downside_risk_pct : % de simulaciones con beneficio negativo
    """
    if n_runs is None:
        n_runs = MC_RUNS

    # Evaluación base (sin ruido) para obtener la estimación central de demanda
    base = system_model.evaluate(price, marketing)
    base_demand = base["demand"]

    # Ruido proporcional a la demanda base (desviación estándar = 10% de demanda)
    noise_std = base_demand * 0.10

    profits = np.empty(n_runs)
    demands = np.empty(n_runs)

    for i in range(n_runs):
        # Perturbación gaussiana sobre la demanda base
        noisy_demand = max(0.0, base_demand + np.random.normal(0.0, noise_std))

        revenue = price * noisy_demand
        cost = noisy_demand * system_model.unit_cost
        profit = revenue - cost

        profits[i] = profit
        demands[i] = noisy_demand

    downside_risk_pct = float(np.mean(profits < 0) * 100)

    return {
        "price": price,
        "marketing": marketing,
        "expected_profit": float(np.mean(profits)),
        "profit_std": float(np.std(profits)),
        "profit_p10": float(np.percentile(profits, 10)),
        "profit_p90": float(np.percentile(profits, 90)),
        "expected_demand": float(np.mean(demands)),
        "demand_std": float(np.std(demands)),
        "downside_risk_pct": downside_risk_pct,
        "n_runs": n_runs,
    }
