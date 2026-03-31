"""
system/system_graph.py
----------------------
Builds the causal Directed Acyclic Graph from the organizational spec.

Edges are derived from ``causal_relationships`` in
``spec/organizational_model.yaml``. To add, remove or rewire causal links,
edit the spec — no code changes required.
"""

import networkx as nx

from spec.spec_loader import get_spec


def build_graph() -> nx.DiGraph:
    """
    Build the causal Directed Acyclic Graph from the organizational spec.
    Each causal_relationship entry in the YAML becomes one or more directed
    edges: from_var → to_var for each from_var in the 'from' list.
    """
    spec = get_spec()
    G = nx.DiGraph()

    for rel in spec.causal_relationships:
        for from_var in rel.from_vars:
            G.add_edge(
                from_var,
                rel.to_var,
                type=rel.rel_type,
                description=rel.description,
            )

    return G
