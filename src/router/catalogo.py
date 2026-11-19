"""Consultas parametrizadas y de solo lectura al catálogo de Postgres."""

import logging
import os
import re
from collections.abc import Mapping, Sequence
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logger = logging.getLogger(__name__)
CATALOGO_NO_DISPONIBLE = "catálogo no disponible"
TIMEOUT = 5
# El checkpointer usa hasta 2 conexiones; el catálogo abre como máximo 1 más
# por proceso, incluso cuando el agente solicita herramientas en paralelo.
_CONSULTA_EN_CURSO = BoundedSemaphore(1)


def _valor_json(value: Any) -> Any:
    """Conserva los numeric como números serializables por las herramientas."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def consultar_catalogo(
    select: str, parametros: Mapping[str, Any] | Sequence[Any] = ()
) -> list[dict[str, Any]] | str:
    """Ejecuta un SELECT fijo con valores separados del SQL y cierra la conexión.

    El SQL lo escribe el código de la aplicación, nunca el usuario ni el modelo.
    Ante fallos de conexión o consulta devuelve CATALOGO_NO_DISPONIBLE, no filas
    vacías: así el agente distingue una caída de una búsqueda sin resultados.
    """
    sql = select.strip().removesuffix(";").rstrip()
    if (
        not re.match(r"\ASELECT\b", sql, flags=re.IGNORECASE)
        or ";" in sql
        or re.search(r"\bINTO\b", sql, flags=re.IGNORECASE)
    ):
        raise ValueError("El catálogo solo admite una sentencia SELECT sin INTO.")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.warning("Catálogo no disponible: DATABASE_URL no está configurada.")
        return CATALOGO_NO_DISPONIBLE
    if not _CONSULTA_EN_CURSO.acquire(timeout=TIMEOUT):
        logger.warning("Catálogo ocupado; se agotó el tiempo de espera.")
        return CATALOGO_NO_DISPONIBLE

    try:
        with closing(
            psycopg.connect(
                database_url,
                autocommit=False,
                prepare_threshold=None,
                row_factory=dict_row,
                connect_timeout=TIMEOUT,
                options=(
                    "-c default_transaction_read_only=on "
                    "-c statement_timeout=5000 -c lock_timeout=3000"
                ),
            )
        ) as connection:
            # La propia transacción es de solo lectura, además de validar que
            # la consulta sea un único SELECT fijo. closing() la termina y
            # cierra la conexión también ante una excepción o un retorno.
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute(sql, parametros)
                # Los numeric de Postgres llegan como Decimal. Las herramientas
                # necesitan valores JSON, sin alterar ni calcular sus importes.
                return [
                    {key: _valor_json(value) for key, value in row.items()}
                    for row in cursor.fetchall()
                ]
    except (psycopg.Error, OSError) as exc:
        # No registrar la URL, los parámetros ni errores que puedan contenerlos.
        logger.warning("Catálogo no disponible (%s).", type(exc).__name__)
        return CATALOGO_NO_DISPONIBLE
    finally:
        _CONSULTA_EN_CURSO.release()
