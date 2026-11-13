import os
import logging
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .prompts import (
    GENERICA_FALLBACK,
    GENERICA_PROMPT,
    POSTVENTA_PROMPT,
    PREVENTA_PROMPT,
    ROUTER_PROMPT,
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logger = logging.getLogger(__name__)
TIENDA_PATH = Path(__file__).resolve().parents[2] / "data" / "tienda.md"


class Decision(BaseModel):
    ruta: Literal["preventa", "postventa", "generica"] = Field(
        description="A qué agente va el mensaje."
    )
    motivo: str = Field(description="Una frase: por qué esa ruta.")


class RouterState(TypedDict, total=False):
    mensaje: str
    ruta: str
    motivo: str
    respuesta: str
    messages: Annotated[list[BaseMessage], add_messages]


def _last_user_message(state: RouterState) -> str:
    for message in reversed(state.get("messages", [])):
        if message.type == "human":
            return str(message.content)
    return state.get("mensaje", "")


def router(state: RouterState) -> dict[str, str]:
    mensaje = _last_user_message(state)
    modelo = ChatGoogleGenerativeAI(
        model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
        temperature=0,
    )
    decision = modelo.with_structured_output(Decision).invoke(
        [{"role": "system", "content": ROUTER_PROMPT},
         {"role": "user", "content": mensaje}]
    )
    return {"mensaje": mensaje, "ruta": decision.ruta, "motivo": decision.motivo}


def _conversation(state: RouterState) -> list[BaseMessage]:
    messages = list(state.get("messages", []))
    if not messages or messages[-1].type != "human":
        messages.append(HumanMessage(content=state.get("mensaje", _last_user_message(state))))
    return messages


def _response_update(state: RouterState, respuesta: str) -> dict[str, object]:
    conversation = _conversation(state)
    new_messages = conversation[len(state.get("messages", [])):]
    return {
        "respuesta": respuesta,
        "messages": [*new_messages, AIMessage(content=respuesta)],
    }


def _agent_response(prompt: str, state: RouterState) -> dict[str, object]:
    mensaje = state.get("mensaje", _last_user_message(state))
    respuesta = prompt.format(mensaje=mensaje)
    return _response_update(state, respuesta)


def agente_preventa(state: RouterState) -> dict[str, object]:
    return _agent_response(PREVENTA_PROMPT, state)


def agente_postventa(state: RouterState) -> dict[str, object]:
    return _agent_response(POSTVENTA_PROMPT, state)


def respuesta_generica(state: RouterState) -> dict[str, object]:
    respuesta = GENERICA_FALLBACK
    try:
        tienda = TIENDA_PATH.read_text(encoding="utf-8")
        modelo = ChatGoogleGenerativeAI(
            model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
            temperature=0,
        )
        result = modelo.invoke([
            SystemMessage(content=GENERICA_PROMPT.format(tienda=tienda)),
            *_conversation(state),
        ])
        texto = result.text.strip()
        if texto:
            respuesta = "\n".join(texto.splitlines()[:3]).strip()
        else:
            logger.warning("Respuesta genérica vacía; se usa la frase de respaldo.")
    except Exception as exc:
        logger.warning(
            "No se pudo generar la respuesta genérica (%s); se usa la frase de respaldo.",
            type(exc).__name__,
        )
    return _response_update(state, respuesta)


def _seleccionar_ruta(state: RouterState) -> str:
    return state["ruta"]


builder = StateGraph(RouterState)
builder.add_node("router", router)
builder.add_node("agente_preventa", agente_preventa)
builder.add_node("agente_postventa", agente_postventa)
builder.add_node("respuesta_generica", respuesta_generica)
builder.add_edge(START, "router")
builder.add_conditional_edges(
    "router",
    _seleccionar_ruta,
    {
        "preventa": "agente_preventa",
        "postventa": "agente_postventa",
        "generica": "respuesta_generica",
    },
)
builder.add_edge("agente_preventa", END)
builder.add_edge("agente_postventa", END)
builder.add_edge("respuesta_generica", END)

def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Compila una vez por sesión; el propietario gestiona el checkpointer."""
    return builder.compile(checkpointer=checkpointer)
