"""
system/system_graph.py
----------------------
Builds the causal Directed Acyclic Graph from the organizational spec.

Edges are derived from ``causal_relationships`` in
``spec/organizational_model.yaml``. To add, remove or rewire causal links,
edit the spec — no code changes required.
"""

from __future__ import annotations

from typing import Any, List

import networkx as nx

from spec.spec_loader import get_spec


def _assert_acyclic(G: nx.DiGraph) -> None:
    """Raise ValueError if *G* contains a directed cycle."""
    if not nx.is_directed_acyclic_graph(G):
        cycles = list(nx.simple_cycles(G))
        cycle_str = " → ".join(cycles[0]) if cycles else "unknown"
        raise ValueError(
            f"Causal graph contains a cycle: {cycle_str}. "
            "The organizational spec must define an acyclic causal model."
        )


def assert_dag_acyclic(relationships: List[Any]) -> None:
    """Build a minimal DiGraph from *relationships* and assert it is acyclic.

    Each element must expose ``.from_vars`` (list[str]) and ``.to_var`` (str).
    Raises ValueError with a descriptive message if a cycle is detected.
    Called by spec_loader._parse_raw() and, at graph-build time, by build_graph().
    """
    G: nx.DiGraph = nx.DiGraph()
    for rel in relationships:
        for fv in rel.from_vars:
            G.add_edge(fv, rel.to_var)
    _assert_acyclic(G)


def build_graph() -> nx.DiGraph:
    """Build the causal Directed Acyclic Graph from the organizational spec.

    Each causal_relationship entry in the YAML becomes one or more directed
    edges: from_var → to_var for each from_var in the 'from' list.

    Raises ValueError if the resulting graph contains a cycle (item 3.3).
    """
    spec = get_spec()
    G: nx.DiGraph = nx.DiGraph()

    for rel in spec.causal_relationships:
        for from_var in rel.from_vars:
            G.add_edge(
                from_var,
                rel.to_var,
                type=rel.rel_type,
                description=rel.description,
            )

    _assert_acyclic(G)
    return G
