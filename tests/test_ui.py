import pytest


def test_interfaz_disponible_sin_exponer_la_clave(monkeypatch, api_client):
    secret = "secreto-que-no-debe-aparecer-en-la-ui"
    monkeypatch.setenv("API_KEY", secret)
    response = api_client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert '<html lang="es">' in response.text
    assert "Recorrido del agente" in response.text
    assert 'type="password"' in response.text
    assert 'src="/static/chat.js"' in response.text
    assert secret not in response.text
    assert "/" not in api_client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("asset, content_type", [
    ("chat.css", "text/css"), ("chat.js", "javascript"),
])
def test_recursos_de_interfaz_son_locales_y_no_contienen_secretos(
    monkeypatch, api_client, asset, content_type
):
    secret = "otro-secreto-que-no-debe-aparecer"
    monkeypatch.setenv("API_KEY", secret)
    response = api_client.get(f"/static/{asset}")
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert secret not in response.text


def test_interfaz_no_puede_leer_archivos_privados(api_client):
    for path in ("/.env", "/static/.env", "/static/%2e%2e/.env"):
        assert api_client.get(path).status_code == 404


def test_contrato_del_chat_documenta_los_saltos(api_client):
    schema = api_client.get("/openapi.json").json()
    field = schema["components"]["schemas"]["ChatResponse"]["properties"]["saltos"]
    assert field["type"] == "array"
    assert field["items"]["type"] == "string"
    assert schema["paths"]["/chat"]["post"]["security"] == [{"APIKey": []}]
