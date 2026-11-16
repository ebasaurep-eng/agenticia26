"""Cliente A2A del agente de redes; la configuración procede únicamente de .env."""

import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")
TIMEOUT = 60
REDES_NO_DISPONIBLES = "el agente de redes no está disponible"


async def preguntar_redes(texto: str, hilo: str) -> str:
    """Consulta el agente externo y devuelve su texto completo, sin resumir.

    Los fallos se propagan al llamador para que la herramienta o el visor puedan
    manejarlos sin exponer credenciales ni confundir un error con falta de noticias.
    """
    url = os.getenv("INTEL_URL", "").strip()
    token = os.getenv("INTEL_TOKEN", "").strip()
    if not url or not token:
        raise ValueError("Configura INTEL_URL e INTEL_TOKEN antes de consultar redes.")
    if not texto.strip() or not hilo.strip():
        raise ValueError("La consulta de redes necesita texto e hilo de conversación.")

    # Importación diferida: la API y el catálogo siguen disponibles incluso si
    # todavía no se ha instalado la nueva dependencia del cliente A2A.
    from a2a.client import ClientConfig, create_client
    from a2a.helpers.proto_helpers import get_stream_response_text, new_text_message
    from a2a.types import Role, SendMessageRequest

    # El límite total incluye tanto resolver la ficha pública como enviar el
    # mensaje. No hay reintentos automáticos de esta consulta lenta.
    async with asyncio.timeout(TIMEOUT):
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        ) as http:
            client = await create_client(
                url,
                client_config=ClientConfig(httpx_client=http, streaming=False),
            )
            request = SendMessageRequest(
                message=new_text_message(texto, role=Role.ROLE_USER, context_id=hilo)
            )
            partes: list[str] = []
            async for response in client.send_message(request):
                contenido = get_stream_response_text(response)
                if contenido:
                    partes.append(contenido)

    respuesta = "\n".join(partes).strip()
    if not respuesta:
        raise ValueError("El agente de redes no devolvió contenido de texto.")
    return respuesta
