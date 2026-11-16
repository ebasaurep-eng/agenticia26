"""Muestra productos del catálogo o cuenta cuántos hay por categoría."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.router.catalogo import consultar_catalogo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("texto", nargs="?", help="Texto contenido en el nombre del producto")
    args = parser.parse_args()

    if args.texto is None:
        filas = consultar_catalogo(
            """SELECT categoria, COUNT(*) AS cantidad
               FROM catalogo.productos_unicos
               GROUP BY categoria
               ORDER BY categoria""",
            (),
        )
    else:
        filas = consultar_catalogo(
            """SELECT sku_id, nombre,
                      NULLIF(BTRIM(precio_internet::text), '')::numeric AS precio_internet,
                      NULLIF(BTRIM(rating::text), '')::numeric AS rating
               FROM catalogo.productos_unicos
               WHERE strpos(lower(COALESCE(nombre, '')), lower(%(texto)s::text)) > 0
               ORDER BY rating DESC NULLS LAST, precio_internet ASC, sku_id
               LIMIT %(limite)s""",
            {"texto": args.texto, "limite": 10},
        )

    if isinstance(filas, str):
        print(filas)
        return 1
    if not filas:
        print("No hay productos que coincidan." if args.texto is not None else "Catálogo vacío.")
    for fila in filas:
        if args.texto is None:
            print(f"{fila['categoria']}: {fila['cantidad']}")
        else:
            precio = fila["precio_internet"]
            precio_texto = f"${precio:,.0f}".replace(",", ".") if precio is not None else "sin precio"
            rating = fila["rating"]
            rating_texto = f"{rating}/5" if rating is not None else "sin rating"
            print(f"{fila['sku_id']} | {fila['nombre']} | {precio_texto} | {rating_texto}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
