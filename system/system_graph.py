import networkx as nx


def build_graph():
    G = nx.DiGraph()

    G.add_edges_from(
        [
            ("price", "demand"),
            ("marketing", "demand"),
            ("demand", "revenue"),
            ("demand", "cost"),
            ("revenue", "profit"),
            ("cost", "profit"),
        ]
    )

    return G
