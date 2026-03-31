"""
system/system_model.py
----------------------
Causal business model evaluation engine.

``SystemModel.evaluate()`` propagates input values through the causal DAG in
topological order. Each derived node is computed by a registered formula in
``_NODE_FORMULAS``; adding a new causal variable requires only registering its
formula and adding the corresponding edge to the graph — no changes to the
traversal logic.

Business parameters (``unit_cost``, etc.) are loaded from the organizational
spec; ``config/settings.py`` is used as a fallback if the spec is unavailable.
"""

from __future__ import annotations

import pickle
from typing import Dict

import networkx as nx

from system.system_graph import build_graph

# ── Load business parameters from spec; fall back to config if unavailable ────
try:
    from spec.spec_loader import get_spec

    _USE_SPEC = True
except ImportError:
    _USE_SPEC = False

if not _USE_SPEC:
    from config.settings import UNIT_COST as _FALLBACK_UNIT_COST


# ── Registro de fórmulas para nodos derivados ─────────────────────────────────
# Cada fórmula recibe el dict de valores ya calculados
# y devuelve el valor del nodo.
# Para añadir un nuevo nodo: registrarlo aquí y añadir la arista en system_graph.py
_NODE_FORMULAS: Dict[str, callable] = {
    "revenue": lambda v: v["price"] * v["demand"],
    "cost": lambda v: v["demand"] * v["_unit_cost"],
    "profit": lambda v: v["revenue"] - v["cost"],
}


class SystemModel:
    """
    Representa el modelo causal del sistema organizacional.

    La evaluación propaga valores a través del DAG en orden topológico,
    usando el modelo ML para los nodos estimados y las fórmulas registradas
    para los nodos derivados. El grafo es la fuente de verdad estructural.
    """

    def __init__(self):
        # ── Cargar parámetros desde spec o fallback ───────────────────────────
        if _USE_SPEC:
            spec = get_spec()
            model_path = spec.ml_model_path
            self.unit_cost = spec.business_parameters.get("unit_cost", 10.0)
            self.spec = spec
        else:
            model_path = "models/demand_model.pkl"
            self.unit_cost = _FALLBACK_UNIT_COST

        # ── Cargar modelo ML ──────────────────────────────────────────────────
        with open(model_path, "rb") as f:
            self.demand_model = pickle.load(f)

        # ── Construir DAG causal y pre-calcular orden de evaluación ───────────
        self.graph = build_graph()
        self._eval_order = list(nx.topological_sort(self.graph))

    def evaluate(self, price: float, marketing: float) -> dict:
        """
        Evalúa el modelo organizacional para un punto (price, marketing) dado.

        Propaga los valores a través del DAG en orden topológico:
          1. Inicializa los nodos de decisión con los valores de entrada.
          2. Para cada nodo en orden topológico:
             - Si ya tiene valor → continúa.
             - Si es un nodo ML-estimado → predice con el modelo.
             - Si tiene fórmula registrada → calcula con la fórmula.
          3. Devuelve el dict completo de todos los nodos (excluye internos).

        Args:
            price:     Precio unitario del producto.
            marketing: Inversión en marketing del período.

        Returns:
            Dict con los valores de todas las variables del modelo:
            price, marketing, demand, revenue, cost, profit.
        """
        # Inicializar nodos conocidos (decisiones + parámetros internos)
        values: Dict[str, float] = {
            "price": price,
            "marketing": marketing,
            "_unit_cost": self.unit_cost,  # prefijo _ = variable interna
        }

        # Propagar en orden topológico
        for node in self._eval_order:
            if node in values:
                continue  # ya calculado

            if node == "demand":
                # Nodo estimado por ML
                values["demand"] = float(
                    self.demand_model.predict([[price, marketing]])[0]
                )
            elif node in _NODE_FORMULAS:
                # Nodo calculado por fórmula registrada
                values[node] = _NODE_FORMULAS[node](values)
            # Unknown nodes are skipped silently

        # Eliminar variables internas del output
        return {k: v for k, v in values.items() if not k.startswith("_")}
