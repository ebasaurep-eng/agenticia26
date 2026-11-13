import pytest


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
def test_chat_sin_clave_valida_responde_401(
    monkeypatch, configured_key, headers, api_runtime, api_client
):
    if configured_key is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", configured_key)
    response = api_client.post(
        "/chat", headers=headers, json={"user_id": "usuario-test", "texto": "hola"}
    )

    assert response.status_code == 401
    assert "X-API-Key" in response.json()["detail"]
    api_runtime.graph.ainvoke.assert_not_called()


def test_chat_con_clave_responde_200(monkeypatch, api_runtime, api_client):
    monkeypatch.setenv("API_KEY", "clave-de-prueba")
    expected = {
        "ruta": "preventa",
        "motivo": "Consulta disponibilidad de un producto.",
        "respuesta": "Respuesta de prueba.",
    }
    invoke = api_runtime.graph.ainvoke
    invoke.return_value = expected

    response = api_client.post(
        "/chat",
        headers={"X-API-Key": "clave-de-prueba"},
        json={"user_id": "usuario-test", "texto": "¿Tienen stock?"},
    )
    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["memoria"] == "ram"
    schema = api_client.get("/openapi.json").json()
    assert schema["paths"]["/chat"]["post"]["security"] == [{"APIKey": []}]
    assert "security" not in schema["paths"]["/health"]["get"]
    assert schema["components"]["securitySchemes"]["APIKey"]["name"] == "X-API-Key"

    assert response.status_code == 200
    assert response.json() == expected
    invoke.assert_awaited_once()
    assert invoke.call_args.kwargs["config"]["configurable"]["thread_id"] == "usuario-test"
