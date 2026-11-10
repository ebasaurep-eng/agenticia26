"""Consulta y comprueba la información del webhook configurado en Telegram."""

import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> int:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    public_url = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    if not token or not public_url:
        print("Faltan TELEGRAM_TOKEN o PUBLIC_URL en .env.")
        return 1

    endpoint = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    try:
        response = httpx.get(endpoint, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"No se pudo consultar el webhook ({type(exc).__name__}).")
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload.get("ok"):
        return 1

    info = payload.get("result", {})
    expected_url = f"{public_url}/telegram"
    configured_url = info.get("url", "")
    pending = info.get("pending_update_count", 0)
    print(f"URL correcta: {configured_url == expected_url}")
    print(f"Updates pendientes: {pending}")
    if info.get("last_error_message"):
        print(f"Último error de Telegram: {info['last_error_message']}")
    no_errors = not info.get("last_error_message") and not pending
    print(f"Sin errores ni pendientes: {no_errors}")
    return 0 if configured_url == expected_url and no_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
