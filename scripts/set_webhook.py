"""Registra el webhook de Telegram usando variables cargadas desde .env."""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> int:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    secret = os.getenv("TELEGRAM_SECRET", "").strip()
    public_url = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
    if not token or not secret or not public_url:
        print("Faltan TELEGRAM_TOKEN, TELEGRAM_SECRET o PUBLIC_URL en .env.")
        return 1

    endpoint = f"https://api.telegram.org/bot{token}/setWebhook"
    try:
        response = httpx.post(
            endpoint,
            json={"url": f"{public_url}/telegram", "secret_token": secret},
            timeout=20.0,
        )
        print(response.text)
        body = response.json()
        return 0 if response.is_success and isinstance(body, dict) and body.get("ok") else 1
    except (httpx.HTTPError, ValueError) as exc:
        print(f"No se pudo configurar el webhook ({type(exc).__name__}).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
