"""
app.py  ← CORREGIDO
─────────────────────
Cambios:
  1. Manejo de excepciones en el bucle principal: los errores del agente no
     terminan el proceso, se muestran al usuario y el bucle continúa.
  2. Separación entre KeyboardInterrupt y errores de agente.
  3. Cabecera de bienvenida con instrucciones básicas de uso.
"""

from agents.workflow import build_graph

WELCOME = """
╔══════════════════════════════════════════════════════════╗
║        Decision Intelligence Agent                      ║
╠══════════════════════════════════════════════════════════╣
║  Ask business questions about pricing and marketing.    ║
║  Examples:                                              ║
║    • What price should maximise profit?                 ║
║    • What happens if I set price to 30?                 ║
║    • How does the demand model work?                    ║
║  Type 'exit' to quit.                                   ║
╚══════════════════════════════════════════════════════════╝
"""


def main():
    print(WELCOME)
    graph = build_graph()

    while True:
        try:
            query = input("Ask a business question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not query:
            continue

        if query.lower() == "exit":
            print("Goodbye.")
            break

        try:
            result = graph.invoke({"query": query})
            answer = result.get("answer", "No answer generated.")
            print(f"\n{answer}\n")
        except Exception as exc:
            print(f"\n[Error] Agent failed: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
