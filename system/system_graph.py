"""
system/system_graph.py  (MODIFIED — Mejora 1: spec-driven)
───────────────────────────────────────────────────────────
The causal DAG is no longer hardcoded.
Edges are derived directly from causal_relationships in the spec YAML.

To add, remove or rewire causal links: edit spec/organizational_model.yaml.
No code changes required.
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
