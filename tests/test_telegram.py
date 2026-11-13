import importlib

api_module = importlib.import_module("api.app")


class FakeTelegramResponse:
    status_code = 200
    is_error = False

    @staticmethod
    def json():
        return {"ok": True}


class FakeAsyncClient:
    calls = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, *, json):
        self.calls.append((url, json))
        return FakeTelegramResponse()


def test_telegram_authenticates_routes_and_replies(monkeypatch, api_runtime, api_client):
    monkeypatch.setenv("TELEGRAM_SECRET", "test-secret")
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:test-token")
    FakeAsyncClient.calls = []
    graph_calls = []

    async def invoke(state, *, config):
        graph_calls.append((state, config))
        return {
            "ruta": "preventa",
            "motivo": "Consulta por un producto.",
            "respuesta": "Respuesta de preventa.",
        }

    monkeypatch.setattr(api_runtime.graph, "ainvoke", invoke)
    monkeypatch.setattr(api_module.httpx, "AsyncClient", FakeAsyncClient)
    client = api_client

    response = client.post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"message": {"chat": {"id": 456}, "text": "¿Tienen stock?"}},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert graph_calls[0][1]["configurable"]["thread_id"] == "456"
    assert FakeAsyncClient.calls[0][1] == {
        "chat_id": 456,
        "text": "Respuesta de preventa.",
    }


def test_telegram_rejects_wrong_secret_without_processing(monkeypatch, api_client):
    monkeypatch.setenv("TELEGRAM_SECRET", "test-secret")
    client = api_client
    response = client.post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json={"message": {"chat": {"id": 456}, "text": "hola"}},
    )
    assert response.status_code == 403
    assert "test-secret" not in response.text


def test_telegram_ignores_updates_without_text(monkeypatch, api_client):
    monkeypatch.setenv("TELEGRAM_SECRET", "test-secret")
    client = api_client
    response = client.post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"message": {"chat": {"id": 456}, "photo": []}},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_telegram_acknowledges_model_failure_with_200(monkeypatch, api_runtime, api_client):
    monkeypatch.setenv("TELEGRAM_SECRET", "test-secret")

    async def fail_invoke(*_args, **_kwargs):
        raise RuntimeError("fallo simulado del modelo")

    monkeypatch.setattr(api_runtime.graph, "ainvoke", fail_invoke)
    client = api_client
    response = client.post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"message": {"chat": {"id": 456}, "text": "hola"}},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
