"""Ciclo de vida de la memoria del router, compartido por API, CLI y scripts."""

import logging
import os
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from .graph import build_graph


logger = logging.getLogger(__name__)
CONNECT_TIMEOUT = 5
CONNECTION_OPTIONS = {
    "autocommit": True,
    "prepare_threshold": 0,
    "row_factory": dict_row,
    "connect_timeout": CONNECT_TIMEOUT,
    "options": "-c statement_timeout=10000 -c lock_timeout=5000",
}


@dataclass
class RouterRuntime:
    graph: Any
    checkpointer: Any
    memoria: Literal["ram", "postgres"]


@contextmanager
def open_graph():
    """Abre un pool síncrono por proceso de terminal y lo cierra al terminar."""
    pool = None
    saver = MemorySaver()
    memoria = "ram"
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        try:
            pool = ConnectionPool(
                conninfo=database_url,
                min_size=1,
                max_size=2,
                open=False,
                timeout=CONNECT_TIMEOUT,
                kwargs=CONNECTION_OPTIONS.copy(),
                check=ConnectionPool.check_connection,
            )
            pool.open(wait=True, timeout=CONNECT_TIMEOUT)
            postgres = PostgresSaver(pool)
            postgres.setup()
            saver = postgres
            memoria = "postgres"
        except Exception as exc:
            if pool is not None:
                pool.close()
                pool = None
            logger.warning(
                "Memoria RAM: Postgres no disponible al arrancar (%s).",
                type(exc).__name__,
            )
    else:
        logger.warning("Memoria RAM: DATABASE_URL no está configurada.")

    try:
        yield RouterRuntime(build_graph(saver), saver, memoria)
    finally:
        if pool is not None:
            pool.close()


@asynccontextmanager
async def open_async_graph():
    """Abre un pool asíncrono por lifespan de FastAPI, nunca por petición."""
    pool = None
    saver = MemorySaver()
    memoria = "ram"
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        try:
            pool = AsyncConnectionPool(
                conninfo=database_url,
                min_size=1,
                max_size=2,
                open=False,
                timeout=CONNECT_TIMEOUT,
                kwargs=CONNECTION_OPTIONS.copy(),
                check=AsyncConnectionPool.check_connection,
            )
            await pool.open(wait=True, timeout=CONNECT_TIMEOUT)
            postgres = AsyncPostgresSaver(pool)
            await postgres.setup()
            saver = postgres
            memoria = "postgres"
        except Exception as exc:
            if pool is not None:
                await pool.close()
                pool = None
            logger.warning(
                "Memoria RAM: Postgres no disponible al arrancar (%s).",
                type(exc).__name__,
            )
    else:
        logger.warning("Memoria RAM: DATABASE_URL no está configurada.")

    try:
        yield RouterRuntime(build_graph(saver), saver, memoria)
    finally:
        if pool is not None:
            await pool.close()
