import logging
import os
import hmac
import secrets
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field

from src.router.runtime import open_async_graph

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="APIKey",
    description="Clave configurada en API_KEY. Necesaria solo para /chat.",
    auto_error=False,
)


async def verificar_api_key(key: str | None = Security(api_key_header)) -> None:
    expected_key = os.getenv("API_KEY", "")
    if (
        not expected_key
        or not key
        or not secrets.compare_digest(key.encode("utf-8"), expected_key.encode("utf-8"))
    ):
        raise HTTPException(
            status_code=401,
            detail="Clave de API ausente o inválida. Envía una clave válida en X-API-Key.",
        )


TAGS_METADATA = [
    {"name": "salud", "description": "Estado y configuración básica de la API."},
    {"name": "chat", "description": "Enrutamiento de mensajes del chat de ecommerce."},
    {"name": "telegram", "description": "Webhook de Telegram para enrutar mensajes de texto."},
]


class ChatRequest(BaseModel):
    """Mensaje del usuario que se enviará al router del ecommerce."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"user_id": "usuario-123", "texto": "¿Tienen la polera azul en talla M?"}]
        }
    )

    user_id: str = Field(
        ..., description="Identificador estable del usuario, usado para conservar su memoria.",
        examples=["usuario-123"], min_length=1,
    )
    texto: str = Field(
        ..., description="Mensaje que el router debe clasificar.",
        examples=["¿Tienen la polera azul en talla M?"], min_length=1,
    )


class ChatResponse(BaseModel):
    """Resultado del enrutamiento y respuesta del agente destino."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "ruta": "preventa",
                    "motivo": "Consulta disponibilidad y talla de un producto.",
                    "respuesta": "Soy el agente de preventa. Recibí: ¿Tienen la polera azul en talla M?. Pronto podré ayudarte con productos y compras.",
                }
            ]
        }
    )

    ruta: Literal["preventa", "postventa", "generica"] = Field(
        ..., description="Ruta seleccionada por el router.", examples=["preventa"]
    )
    motivo: str = Field(
        ..., description="Motivo breve de la clasificación.",
        examples=["Consulta disponibilidad y talla de un producto."],
    )
    respuesta: str = Field(
        ..., description="Respuesta del agente asignado.",
        examples=["Soy el agente de preventa. Recibí: ¿Tienen la polera azul en talla M?. Pronto podré ayudarte con productos y compras."],
    )


class HealthResponse(BaseModel):
    ok: bool = Field(..., description="Indica que la API está disponible.", examples=[True])
    modelo: str = Field(..., description="Modelo configurado para el router.", examples=["gemini-3.5-flash-lite"])
    memoria: Literal["ram", "postgres"] = Field(
        ..., description="Memoria activa del grafo en este proceso.", examples=["postgres"]
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with open_async_graph() as runtime:
        app.state.router = runtime
        yield


app = FastAPI(
    lifespan=lifespan,
    title="Ecommerce Router API",
    version="1.0.0",
    description=(
        "API para enrutar mensajes de un ecommerce. El router clasifica cada mensaje "
        "en una de tres rutas: preventa, postventa o generica."
    ),
    openapi_tags=TAGS_METADATA,
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["salud"],
    summary="Comprobar estado de la API",
    description="Devuelve disponibilidad de la API y el nombre del modelo configurado.",
)
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        ok=True,
        modelo=os.getenv("MODELO", "gemini-3.5-flash-lite"),
        memoria=request.app.state.router.memoria,
    )


@app.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Security(verificar_api_key)],
    tags=["chat"],
    summary="Enrutar un mensaje del chat",
    description="Clasifica el mensaje y devuelve la ruta, el motivo y la respuesta del agente destino.",
    responses={
        200: {"description": "Mensaje clasificado y respondido.", "model": ChatResponse},
        401: {"description": "Cabecera X-API-Key ausente o inválida."},
        422: {"description": "El body falta o no cumple el esquema ChatRequest."},
        502: {"description": "El modelo de enrutamiento no pudo procesar el mensaje."},
    },
)
async def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    try:
        result = await http_request.app.state.router.graph.ainvoke(
            {"messages": [HumanMessage(content=request.texto)]},
            config={"configurable": {"thread_id": request.user_id}},
        )
        return ChatResponse(
            ruta=result["ruta"], motivo=result["motivo"], respuesta=result["respuesta"]
        )
    except Exception as exc:
        logger.exception("Fallo al enrutar el mensaje de chat")
        raise HTTPException(
            status_code=502,
            detail="No se pudo procesar el mensaje con el modelo de enrutamiento. Inténtalo de nuevo.",
        ) from exc


@app.post(
    "/telegram",
    tags=["telegram"],
    include_in_schema=False,
    summary="Recibir un update de Telegram",
)
async def telegram(
    request: Request,
    payload: Any = Body(...),
    telegram_secret: str | None = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> dict[str, bool]:
    configured_secret = os.getenv("TELEGRAM_SECRET", "")
    if (
        not configured_secret
        or not telegram_secret
        or not hmac.compare_digest(
            telegram_secret.encode("utf-8"), configured_secret.encode("utf-8")
        )
    ):
        raise HTTPException(status_code=403, detail="Secreto de webhook inválido.")

    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        return {"ok": True}
    text = message.get("text")
    chat = message.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    if not isinstance(text, str) or not text.strip() or chat_id is None:
        return {"ok": True}

    token = os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_TOKEN no está configurado; update confirmado sin procesar")
        return {"ok": True}

    try:
        result = await request.app.state.router.graph.ainvoke(
            {"messages": [HumanMessage(content=text)]},
            config={"configurable": {"thread_id": str(chat_id)}},
        )
        logger.info("Telegram ruta=%s motivo=%s", result["ruta"], result["motivo"])
    except Exception as exc:
        logger.error("Error ejecutando el router para Telegram (%s)", type(exc).__name__)
        return {"ok": True}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            telegram_response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": result["respuesta"]},
            )
        if telegram_response.is_error:
            logger.error(
                "Telegram sendMessage respondió HTTP %s", telegram_response.status_code
            )
        else:
            response_body = telegram_response.json()
            if not isinstance(response_body, dict) or not response_body.get("ok", False):
                logger.error("Telegram sendMessage devolvió ok=false")
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.error("Error enviando respuesta a Telegram (%s)", type(exc).__name__)

    return {"ok": True}
