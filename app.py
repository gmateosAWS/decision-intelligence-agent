from agents.workflow import build_graph

graph = build_graph()

while True:
    query = input("Ask a business question: ")

    if query == "exit":
        break

    result = graph.invoke({"query": query})

    print(result["answer"])
