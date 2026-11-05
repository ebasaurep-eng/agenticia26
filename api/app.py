import logging
import os
from typing import Any, Literal

from fastapi import Body, FastAPI, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field

from src.router.graph import graph

logger = logging.getLogger(__name__)

TAGS_METADATA = [
    {"name": "salud", "description": "Estado y configuración básica de la API."},
    {"name": "chat", "description": "Enrutamiento de mensajes del chat de ecommerce."},
    {"name": "telegram", "description": "Webhook de Telegram (integración pendiente)."},
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


app = FastAPI(
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
async def health() -> HealthResponse:
    return HealthResponse(ok=True, modelo=os.getenv("MODELO", "gemini-3.5-flash-lite"))


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["chat"],
    summary="Enrutar un mensaje del chat",
    description="Clasifica el mensaje y devuelve la ruta, el motivo y la respuesta del agente destino.",
    responses={
        200: {"description": "Mensaje clasificado y respondido.", "model": ChatResponse},
        422: {"description": "El body falta o no cumple el esquema ChatRequest."},
        502: {"description": "El modelo de enrutamiento no pudo procesar el mensaje."},
    },
)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = graph.invoke(
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
    summary="Webhook provisional de Telegram",
)
async def telegram(_payload: Any = Body(...)) -> dict[str, bool]:
    return {"ok": True}
