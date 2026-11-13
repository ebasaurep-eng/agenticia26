"""Inspecciona los checkpoints persistidos sin invocar el modelo."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.router.runtime import open_graph  # noqa: E402


def listar_hilos(checkpointer) -> None:
    hilos = {}
    for item in checkpointer.list(None):
        config = item.config["configurable"]
        if config.get("checkpoint_ns", ""):
            continue
        thread_id = config["thread_id"]
        fecha = item.checkpoint["ts"]
        resumen = hilos.setdefault(thread_id, {"cantidad": 0, "ultimo": fecha})
        resumen["cantidad"] += 1
        resumen["ultimo"] = max(resumen["ultimo"], fecha)

    print("Hilo | Checkpoints | Último checkpoint (UTC)")
    for thread_id, resumen in sorted(hilos.items()):
        print(f"{thread_id} | {resumen['cantidad']} | {resumen['ultimo']}")
    if not hilos:
        print("No hay hilos guardados.")


def mostrar_conversacion(graph, thread_id: str) -> None:
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    messages = snapshot.values.get("messages", [])
    if not messages:
        print(f"No hay mensajes para el hilo {thread_id!r}.")
        return
    print(f"Hilo: {thread_id}")
    for message in messages:
        print(f"{message.type}: {message.content}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("thread_id", nargs="?", help="Hilo que quieres consultar")
    args = parser.parse_args()

    with open_graph() as runtime:
        if runtime.memoria != "postgres":
            print(
                "Memoria activa: ram. Este proceso no puede ver las conversaciones "
                "en RAM de otro proceso. Configura DATABASE_URL con un Postgres accesible."
            )
            return 1
        if args.thread_id:
            mostrar_conversacion(runtime.graph, args.thread_id)
        else:
            listar_hilos(runtime.checkpointer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
