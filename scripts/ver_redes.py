"""Consulta directamente al agente A2A: python scripts/ver_redes.py "pregunta" [--hilo NOMBRE]."""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.router.a2a_redes import REDES_NO_DISPONIBLES, preguntar_redes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pregunta", help="Pregunta sobre una marca o producto")
    parser.add_argument("--hilo", help="Contexto A2A; por defecto se crea uno nuevo")
    args = parser.parse_args()
    hilo = args.hilo or f"redes-{uuid.uuid4().hex}"
    try:
        respuesta = asyncio.run(preguntar_redes(args.pregunta, hilo))
    except Exception:
        # Las excepciones HTTP pueden contener datos de conexión o autenticación.
        print(REDES_NO_DISPONIBLES, file=sys.stderr)
        return 1
    print(respuesta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
