"""Lista reclamos de Postgres sin invocar el agente: python scripts/ver_reclamos.py [--hilo NOMBRE]."""

import argparse
import os
import sys
from datetime import timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.router.reclamos import ReclamosNoDisponibles, listar_reclamos  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hilo", help="Mostrar solo los reclamos de este thread_id")
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print(
            "DATABASE_URL no está configurada. Los reclamos en RAM pertenecen al "
            "proceso que los creó: este visor no puede leerlos y se pierden al reiniciar."
        )
        return 1
    try:
        filas = listar_reclamos(args.hilo, database_url=database_url)
    except ReclamosNoDisponibles:
        print(
            "No se pudieron leer los reclamos. Comprueba DATABASE_URL y que la API "
            "o la terminal hayan arrancado una vez para crear la tabla."
        )
        return 1
    if not filas:
        print("No hay reclamos guardados para ese hilo." if args.hilo else "No hay reclamos guardados.")
        return 0

    print("Ticket | Pedido | Motivo | Detalle | Hilo | Creado en (UTC)")
    for fila in filas:
        valores = [
            fila["ticket"], fila["numero_pedido"], fila["motivo"], fila["detalle"],
            fila["thread_id"], fila["creado_en"].astimezone(timezone.utc).isoformat(),
        ]
        print(" | ".join(" ".join(str(valor).split()) for valor in valores))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
