"""Punto de entrada para ejecutar los agentes del proyecto.

Los agentes se añadirán en `src/{nombre_agente}/` siguiendo las reglas de
`AGENTS.md`.
"""

import argparse
import importlib
import uuid

from langchain_core.messages import HumanMessage


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecutor de agentes")
    parser.add_argument("agente", help="Nombre del agente dentro de src/")
    parser.add_argument("mensaje", help="Mensaje que recibirá el agente")
    parser.add_argument("--saltos", action="store_true", help="Imprimir nodos recorridos y motivo")
    parser.add_argument("--diagrama", action="store_true", help="Imprimir Mermaid sin ejecutar")
    parser.add_argument("--hilo", help="Thread ID de la conversación (por defecto: uno nuevo)")
    args = parser.parse_args()

    try:
        module = importlib.import_module(f"src.{args.agente}.graph")
    except ModuleNotFoundError as exc:
        if exc.name == f"src.{args.agente}" or exc.name == f"src.{args.agente}.graph":
            parser.error(f"No existe el agente '{args.agente}' en src/{args.agente}/")
        raise

    if args.diagrama:
        graph = module.build_graph()
        print(graph.get_graph().draw_mermaid())
        return

    runtime_module = importlib.import_module(f"src.{args.agente}.runtime")
    config = {"configurable": {"thread_id": args.hilo or str(uuid.uuid4())}}
    with runtime_module.open_graph() as runtime:
        result = runtime.graph.invoke(
            {"messages": [HumanMessage(content=args.mensaje)]}, config=config
        )
    if args.saltos:
        nodo = {
            "preventa": "agente_preventa",
            "postventa": "agente_postventa",
            "generica": "respuesta_generica",
        }[result["ruta"]]
        print(f"router → {nodo}")
        print(f"Motivo: {result['motivo']}")
    print(result["respuesta"])


if __name__ == "__main__":
    main()
