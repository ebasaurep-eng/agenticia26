import json
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.router.runtime import open_graph  # noqa: E402


def main() -> int:
    casos = json.loads((ROOT / "tests" / "casos_router.json").read_text(encoding="utf-8"))
    filas = []
    with open_graph() as runtime:
        for caso in casos:
            resultado = runtime.graph.invoke(
                {"messages": [HumanMessage(content=caso["mensaje"])]},
                config={"configurable": {"thread_id": str(uuid4())}},
            )
            obtenido = resultado["ruta"]
            marca = "✔" if obtenido == caso["esperado"] else "✘"
            filas.append((caso["mensaje"], caso["esperado"], obtenido, marca, resultado["motivo"]))

    encabezados = ("Mensaje", "Esperado", "Obtenido", "OK", "Motivo del router")
    anchos = [
        max(len(encabezados[i]), *(len(str(fila[i])) for fila in filas))
        for i in range(len(encabezados))
    ]

    def mostrar(fila):
        print(" | ".join(str(valor).ljust(anchos[i]) for i, valor in enumerate(fila)))

    mostrar(encabezados)
    print("-+-".join("-" * ancho for ancho in anchos))
    for fila in filas:
        mostrar(fila)

    aciertos = sum(fila[1] == fila[2] for fila in filas)
    total = len(filas)
    print(f"\nAciertos: {aciertos}/{total} ({aciertos / total:.1%})")
    fallados = [fila for fila in filas if fila[1] != fila[2]]
    print("Fallados:")
    if fallados:
        for mensaje, esperado, obtenido, _, motivo in fallados:
            print(f"- {mensaje!r}: esperado={esperado}, obtenido={obtenido}. Motivo: {motivo}")
    else:
        print("- Ninguno")
    return 0 if aciertos >= 13 else 1


if __name__ == "__main__":
    raise SystemExit(main())
