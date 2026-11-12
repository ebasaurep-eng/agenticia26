import importlib
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient


api_module = importlib.import_module("api.app")


@pytest.mark.parametrize(
    "configured_key, headers",
    [
        ("clave-de-prueba", {}),
        ("clave-de-prueba", {"X-API-Key": "clave-incorrecta"}),
        (None, {"X-API-Key": "clave-de-prueba"}),
        ("", {"X-API-Key": "clave-de-prueba"}),
    ],
    ids=["sin-cabecera", "clave-incorrecta", "sin-configuracion", "configuracion-vacia"],
)
def test_chat_sin_clave_valida_responde_401(monkeypatch, configured_key, headers):
    if configured_key is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", configured_key)
    invoke = Mock()
    monkeypatch.setattr(api_module.graph, "invoke", invoke)

    with TestClient(api_module.app) as client:
        response = client.post(
            "/chat", headers=headers, json={"user_id": "usuario-test", "texto": "hola"}
        )

    assert response.status_code == 401
    assert "X-API-Key" in response.json()["detail"]
    invoke.assert_not_called()


def test_chat_con_clave_responde_200(monkeypatch):
    monkeypatch.setenv("API_KEY", "clave-de-prueba")
    expected = {
        "ruta": "preventa",
        "motivo": "Consulta disponibilidad de un producto.",
        "respuesta": "Respuesta de prueba.",
    }
    invoke = Mock(return_value=expected)
    monkeypatch.setattr(api_module.graph, "invoke", invoke)

    with TestClient(api_module.app) as client:
        response = client.post(
            "/chat",
            headers={"X-API-Key": "clave-de-prueba"},
            json={"user_id": "usuario-test", "texto": "¿Tienen stock?"},
        )
        assert client.get("/health").status_code == 200
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/chat"]["post"]["security"] == [{"APIKey": []}]
        assert "security" not in schema["paths"]["/health"]["get"]
        assert schema["components"]["securitySchemes"]["APIKey"]["name"] == "X-API-Key"

    assert response.status_code == 200
    assert response.json() == expected
    invoke.assert_called_once()
    assert invoke.call_args.kwargs["config"]["configurable"]["thread_id"] == "usuario-test"
