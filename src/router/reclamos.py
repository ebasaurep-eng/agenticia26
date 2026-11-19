"""Reclamos persistentes en Postgres y fallback explícito a RAM por proceso."""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any
from uuid import uuid4

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logger = logging.getLogger(__name__)
TIMEOUT = 5
CREAR_TABLA_RECLAMOS = """
CREATE TABLE IF NOT EXISTS reclamos (
    ticket TEXT PRIMARY KEY,
    numero_pedido TEXT NOT NULL,
    motivo TEXT NOT NULL,
    detalle TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
RECLAMOS_NO_DISPONIBLES = "Registro de reclamos no disponible; no se pudo confirmar el guardado."

_database_url: str | None = None
_en_memoria: dict[str, dict[str, Any]] = {}
_lock = Lock()
_aviso_ram = False
# No se mantiene un segundo pool: las escrituras abren como máximo una conexión
# adicional por proceso, con tiempo de espera acotado y cierre al terminar.
_operacion_en_curso = BoundedSemaphore(1)


class ReclamosNoDisponibles(RuntimeError):
    """La operación no pudo confirmarse; no debe anunciarse un ticket creado."""


def configurar_reclamos(database_url: str | None) -> None:
    """Selecciona el backend al arrancar, después de crear la tabla si hay base."""
    global _database_url, _aviso_ram
    with _lock:
        _database_url = database_url or None
        _aviso_ram = not bool(_database_url)
    if not database_url:
        logger.warning(
            "Reclamos en RAM: Postgres no está disponible. "
            "Se perderán al reiniciar y no se comparten entre procesos."
        )


@contextmanager
def _conexion(database_url: str):
    if not _operacion_en_curso.acquire(timeout=TIMEOUT):
        logger.warning("Reclamos ocupados; se agotó el tiempo de espera.")
        raise ReclamosNoDisponibles(RECLAMOS_NO_DISPONIBLES)
    try:
        with psycopg.connect(
            database_url,
            autocommit=True,
            prepare_threshold=None,
            row_factory=dict_row,
            connect_timeout=TIMEOUT,
            options="-c statement_timeout=5000 -c lock_timeout=3000",
        ) as connection:
            yield connection
    except (psycopg.Error, OSError) as exc:
        # No escribir URLs, detalles del reclamo ni datos del cliente en el log.
        logger.warning("Reclamos no disponibles (%s).", type(exc).__name__)
        raise ReclamosNoDisponibles(RECLAMOS_NO_DISPONIBLES) from exc
    finally:
        _operacion_en_curso.release()


def guardar_reclamo(
    numero_pedido: str, motivo: str, detalle: str, thread_id: str
) -> str:
    """Devuelve el ticket solo después de guardar el reclamo en el backend activo."""
    global _aviso_ram
    numero_pedido = numero_pedido.strip().removeprefix("#").strip()
    motivo = motivo.strip()
    detalle = detalle.strip()
    thread_id = thread_id.strip()
    if not all((numero_pedido, motivo, detalle, thread_id)):
        logger.warning("Reclamo no registrado: faltan datos o el hilo de la conversación.")
        raise ReclamosNoDisponibles(RECLAMOS_NO_DISPONIBLES)

    ticket = f"REC-{uuid4().hex.upper()}"
    fila = {
        "ticket": ticket,
        "numero_pedido": numero_pedido,
        "motivo": motivo,
        "detalle": detalle,
        "thread_id": thread_id,
        "creado_en": datetime.now(timezone.utc),
    }
    with _lock:
        database_url = _database_url
        if not database_url:
            if not _aviso_ram:
                logger.warning(
                    "Reclamos en RAM: almacén sin Postgres inicializado; "
                    "se perderán al reiniciar y no se comparten entre procesos."
                )
                _aviso_ram = True
            _en_memoria[ticket] = fila
            return ticket

    # Si una escritura falla con Postgres activo, NO pasar a RAM ni reintentar:
    # podría haberse confirmado en el servidor antes de perder la conexión.
    with _conexion(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO reclamos (ticket, numero_pedido, motivo, detalle, thread_id)
                   VALUES (%(ticket)s, %(numero_pedido)s, %(motivo)s, %(detalle)s, %(thread_id)s)
                   RETURNING ticket""",
                fila,
            )
            guardado = cursor.fetchone()
            if not guardado or not guardado.get("ticket"):
                raise ReclamosNoDisponibles(RECLAMOS_NO_DISPONIBLES)
            return str(guardado["ticket"])


def listar_reclamos(
    thread_id: str | None = None, *, database_url: str | None = None
) -> list[dict[str, Any]]:
    """Lista el backend activo, o una base explícita para el visor independiente."""
    with _lock:
        url = database_url or _database_url
        if not url:
            return sorted(
                [
                    fila.copy() for fila in _en_memoria.values()
                    if thread_id is None or fila["thread_id"] == thread_id
                ],
                key=lambda fila: fila["creado_en"],
                reverse=True,
            )
    with _conexion(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT ticket, numero_pedido, motivo, detalle, thread_id, creado_en
                   FROM reclamos
                   WHERE (%(thread_id)s::text IS NULL OR thread_id = %(thread_id)s::text)
                   ORDER BY creado_en DESC, ticket""",
                {"thread_id": thread_id},
            )
            return cursor.fetchall()
