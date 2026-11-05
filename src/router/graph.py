import os
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .prompts import GENERICA_PROMPT, POSTVENTA_PROMPT, PREVENTA_PROMPT, ROUTER_PROMPT

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


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


def _agent_response(prompt: str, state: RouterState) -> dict[str, object]:
    mensaje = state.get("mensaje", _last_user_message(state))
    respuesta = prompt.format(mensaje=mensaje)
    return {"respuesta": respuesta, "messages": [AIMessage(content=respuesta)]}


def agente_preventa(state: RouterState) -> dict[str, object]:
    return _agent_response(PREVENTA_PROMPT, state)


def agente_postventa(state: RouterState) -> dict[str, object]:
    return _agent_response(POSTVENTA_PROMPT, state)


def respuesta_generica(state: RouterState) -> dict[str, object]:
    return {"respuesta": GENERICA_PROMPT, "messages": [AIMessage(content=GENERICA_PROMPT)]}


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

graph = builder.compile(checkpointer=MemorySaver())
