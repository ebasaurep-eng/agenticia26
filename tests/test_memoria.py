import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from scripts.ver_memoria import listar_hilos, mostrar_conversacion
from src.router import runtime as memory_module


def test_sin_database_url_usa_ram_y_conserva_mensajes(monkeypatch, caplog):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    graph_module = importlib.import_module("src.router.graph")
    model = Mock()
    model.with_structured_output.return_value.invoke.return_value = SimpleNamespace(
        ruta="preventa", motivo="Consulta por un producto."
    )
    monkeypatch.setattr(graph_module, "ChatGoogleGenerativeAI", Mock(return_value=model))
    config = {"configurable": {"thread_id": "prueba-test"}}

    with memory_module.open_graph() as runtime:
        assert runtime.memoria == "ram"
        assert isinstance(runtime.checkpointer, MemorySaver)
        for text in ("me llamo Ana", "tengo hasta 500 mil pesos"):
            runtime.graph.invoke({"messages": [("user", text)]}, config=config)
        state = runtime.graph.get_state(config)
        humans = [message.content for message in state.values["messages"] if message.type == "human"]
        assert humans == ["me llamo Ana", "tengo hasta 500 mil pesos"]
        assert not runtime.graph.get_state(
            {"configurable": {"thread_id": "otro-hilo"}}
        ).values

    assert "DATABASE_URL no está configurada" in caplog.text
    with memory_module.open_graph() as other:
        assert not other.graph.get_state(config).values


@pytest.mark.parametrize("failure", [None, "open", "setup"])
def test_pool_sincrono_se_cierra_y_aplica_fallback(monkeypatch, failure):
    monkeypatch.setenv("DATABASE_URL", "postgresql://datos-ficticios")
    pool = Mock()
    constructor = Mock(return_value=pool)
    constructor.check_connection = Mock()
    saver = Mock(spec=memory_module.PostgresSaver)
    if failure == "open":
        pool.open.side_effect = ConnectionError("No disponible")
    if failure == "setup":
        saver.setup.side_effect = ConnectionError("No disponible")
    monkeypatch.setattr(memory_module, "ConnectionPool", constructor)
    monkeypatch.setattr(memory_module, "PostgresSaver", Mock(return_value=saver))

    with memory_module.open_graph() as runtime:
        assert runtime.memoria == ("ram" if failure else "postgres")
        if not failure:
            pool.close.assert_not_called()
            saver.setup.assert_called_once()

    pool.close.assert_called_once()
    pool.open.assert_called_once_with(wait=True, timeout=5)
    options = constructor.call_args.kwargs
    assert (options["min_size"], options["max_size"]) == (1, 2)
    assert options["open"] is False
    assert options["check"] is constructor.check_connection
    assert options["kwargs"]["autocommit"] is True
    assert options["kwargs"]["prepare_threshold"] == 0


@pytest.mark.parametrize("failure", [None, "open", "setup"])
def test_pool_asincrono_se_cierra_y_aplica_fallback(monkeypatch, failure):
    monkeypatch.setenv("DATABASE_URL", "postgresql://datos-ficticios")
    pool = SimpleNamespace(open=AsyncMock(), close=AsyncMock())
    constructor = Mock(return_value=pool)
    constructor.check_connection = Mock()
    saver = Mock(spec=memory_module.AsyncPostgresSaver)
    saver.setup = AsyncMock()
    if failure == "open":
        pool.open.side_effect = ConnectionError("No disponible")
    if failure == "setup":
        saver.setup.side_effect = ConnectionError("No disponible")
    monkeypatch.setattr(memory_module, "AsyncConnectionPool", constructor)
    monkeypatch.setattr(memory_module, "AsyncPostgresSaver", Mock(return_value=saver))

    async def scenario():
        async with memory_module.open_async_graph() as runtime:
            assert runtime.memoria == ("ram" if failure else "postgres")
            if not failure:
                pool.close.assert_not_awaited()
                saver.setup.assert_awaited_once()

    asyncio.run(scenario())
    pool.close.assert_awaited_once()
    pool.open.assert_awaited_once_with(wait=True, timeout=5)
    options = constructor.call_args.kwargs
    assert (options["min_size"], options["max_size"]) == (1, 2)
    assert options["check"] is constructor.check_connection


def test_api_arranca_si_postgres_falla(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://datos-ficticios")
    pool = SimpleNamespace(
        open=AsyncMock(side_effect=ConnectionError("No disponible")), close=AsyncMock()
    )
    monkeypatch.setattr(memory_module, "AsyncConnectionPool", Mock(return_value=pool))
    api_module = importlib.import_module("api.app")

    with TestClient(api_module.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["memoria"] == "ram"
    pool.close.assert_awaited_once()


def test_api_sin_base_reporta_ram(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    api_module = importlib.import_module("api.app")
    with TestClient(api_module.app) as client:
        assert client.get("/health").json()["memoria"] == "ram"


def test_api_comparte_un_pool_postgres_durante_su_lifespan(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://datos-ficticios")
    monkeypatch.setenv("API_KEY", "clave-test")
    pool = SimpleNamespace(open=AsyncMock(), close=AsyncMock())
    constructor = Mock(return_value=pool)
    saver = Mock(spec=memory_module.AsyncPostgresSaver)
    saver.setup = AsyncMock()
    graph = SimpleNamespace(
        ainvoke=AsyncMock(return_value={
            "ruta": "preventa", "motivo": "Consulta de producto.", "respuesta": "Recibido."
        })
    )
    compile_graph = Mock(return_value=graph)
    monkeypatch.setattr(memory_module, "AsyncConnectionPool", constructor)
    monkeypatch.setattr(memory_module, "AsyncPostgresSaver", Mock(return_value=saver))
    monkeypatch.setattr(memory_module, "build_graph", compile_graph)
    api_module = importlib.import_module("api.app")

    with TestClient(api_module.app) as client:
        assert client.get("/health").json()["memoria"] == "postgres"
        for text in ("primer mensaje", "segundo mensaje"):
            response = client.post(
                "/chat",
                headers={"X-API-Key": "clave-test"},
                json={"user_id": "hilo-api-test", "texto": text},
            )
            assert response.status_code == 200
        constructor.assert_called_once()
        pool.open.assert_awaited_once()
        pool.close.assert_not_awaited()
        saver.setup.assert_awaited_once()
        compile_graph.assert_called_once_with(saver)
        assert graph.ainvoke.await_count == 2
    pool.close.assert_awaited_once()


def test_visor_lista_checkpoints_y_muestra_mensajes(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    graph_module = importlib.import_module("src.router.graph")
    model = Mock()
    model.with_structured_output.return_value.invoke.return_value = SimpleNamespace(
        ruta="preventa", motivo="Consulta por un producto."
    )
    monkeypatch.setattr(graph_module, "ChatGoogleGenerativeAI", Mock(return_value=model))
    config = {"configurable": {"thread_id": "hilo-visor"}}
    with memory_module.open_graph() as runtime:
        runtime.graph.invoke({"messages": [("user", "primer mensaje")]}, config=config)
        runtime.graph.invoke({"messages": [("user", "segundo mensaje")]}, config=config)
        expected_count = len(list(runtime.checkpointer.list(config)))
        listar_hilos(runtime.checkpointer)
        output = capsys.readouterr().out
        assert f"hilo-visor | {expected_count} |" in output
        mostrar_conversacion(runtime.graph, "hilo-visor")
        output = capsys.readouterr().out
        assert output.index("human: primer mensaje") < output.index("human: segundo mensaje")
