import importlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_runtime(monkeypatch):
    """La API se prueba sin consumir conexiones ni cuota del modelo."""
    api_module = importlib.import_module("api.app")
    runtime = SimpleNamespace(
        graph=SimpleNamespace(ainvoke=AsyncMock()), memoria="ram"
    )

    @asynccontextmanager
    async def open_runtime():
        yield runtime

    monkeypatch.setattr(api_module, "open_async_graph", open_runtime)
    return runtime


@pytest.fixture
def api_client(api_runtime):
    api_module = importlib.import_module("api.app")
    with TestClient(api_module.app) as client:
        yield client
