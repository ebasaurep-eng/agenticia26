import os
import logging
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .catalogo import CATALOGO_NO_DISPONIBLE
from .prompts import (
    GENERICA_FALLBACK,
    GENERICA_PROMPT,
    POSTVENTA_AVISO_DERIVACION,
    POSTVENTA_DERIVACION_CREADA,
    POSTVENTA_FALLBACK,
    POSTVENTA_OTROS_RECLAMOS_NO_CONFIRMADOS,
    POSTVENTA_PROMPT,
    POSTVENTA_RECLAMO_CREADO,
    POSTVENTA_RECLAMO_NO_CONFIRMADO,
    PREVENTA_CATALOGO_NO_DISPONIBLE,
    PREVENTA_FALLBACK,
    PREVENTA_PROMPT,
    ROUTER_PROMPT,
)
from .tools import POSTVENTA_TOOLS, PREVENTA_TOOLS

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
    saltos: list[str]


def _last_user_message(state: RouterState) -> str:
    for message in reversed(state.get("messages", [])):
        if message.type == "human":
            return str(message.content)
    return state.get("mensaje", "")


def router(state: RouterState) -> dict[str, object]:
    mensaje = _last_user_message(state)
    conversation = _conversation(state)
    # El router recibe intercambios de chat, no llamadas internas a herramientas.
    historial = [
        message for message in conversation[:-1]
        if message.type in ("human", "ai") and not getattr(message, "tool_calls", None)
    ][-4:]
    modelo = ChatGoogleGenerativeAI(
        model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
        temperature=0,
    )
    decision = modelo.with_structured_output(Decision).invoke(
        [
            SystemMessage(content=ROUTER_PROMPT.format(
                ruta_anterior=state.get("ruta", "ninguna")
            )),
            *historial,
            conversation[-1],
        ]
    )
    return {
        "mensaje": mensaje,
        "ruta": decision.ruta,
        "motivo": decision.motivo,
        "saltos": ["router"],
    }


def _conversation(state: RouterState) -> list[BaseMessage]:
    messages = list(state.get("messages", []))
    if not messages or messages[-1].type != "human":
        messages.append(HumanMessage(content=state.get("mensaje", _last_user_message(state))))
    return messages


def _response_update(state: RouterState, respuesta: str, nodo: str) -> dict[str, object]:
    conversation = _conversation(state)
    new_messages = conversation[len(state.get("messages", [])):]
    return {
        "respuesta": respuesta,
        "messages": [*new_messages, AIMessage(content=respuesta)],
        "saltos": [*state.get("saltos", []), nodo],
    }


def agente_preventa(state: RouterState, config: RunnableConfig) -> dict[str, object]:
    conversation = _conversation(state)
    agent_messages: list[BaseMessage] = []
    respuesta = PREVENTA_FALLBACK
    try:
        modelo = ChatGoogleGenerativeAI(
            model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
            temperature=0,
            timeout=15,
            max_retries=1,
        )
        agente = create_agent(
            model=modelo,
            tools=PREVENTA_TOOLS,
            system_prompt=PREVENTA_PROMPT,
            # La memoria pertenece al grafo exterior. Evita abrir checkpoints
            # internos o usar un AsyncPostgresSaver desde este nodo síncrono.
            checkpointer=False,
            name="agente_preventa",
        )
        # Guardar cada avance permite conservar los saltos y detectar una caída
        # del catálogo aunque después falle el modelo o se agote el bucle ReAct.
        with closing(
            agente.stream(
                {"messages": conversation},
                config={**config, "recursion_limit": 20},
                stream_mode="values",
            )
        ) as snapshots:
            for snapshot in snapshots:
                agent_messages = snapshot["messages"][len(conversation):]
                if any(
                    message.type == "tool" and message.content == CATALOGO_NO_DISPONIBLE
                    for message in agent_messages
                ):
                    # No es necesario pedir otra respuesta al modelo ni volver
                    # a consultar una base caída para avisar al cliente.
                    break
        if agent_messages and agent_messages[-1].type == "ai":
            texto = agent_messages[-1].text.strip()
            if texto and not getattr(agent_messages[-1], "tool_calls", None):
                respuesta = "\n".join(texto.splitlines()[:4]).strip()
    except Exception as exc:
        logger.warning("No se pudo completar la preventa (%s).", type(exc).__name__)

    tools_used = [
        message.name for message in agent_messages
        if message.type == "tool" and message.name
    ]
    if any(
        message.type == "tool" and message.content == CATALOGO_NO_DISPONIBLE
        for message in agent_messages
    ):
        respuesta = PREVENTA_CATALOGO_NO_DISPONIBLE

    # Igual que las otras rutas, persiste usuario y respuesta. Los mensajes
    # internos ReAct son temporales; no quedan llamadas sin resolver si falla.
    update = _response_update(state, respuesta, "agente_preventa")
    update["saltos"] = [*state.get("saltos", []), "agente_preventa", *tools_used]
    return update


def agente_postventa(state: RouterState, config: RunnableConfig) -> dict[str, object]:
    conversation = _conversation(state)
    agent_messages: list[BaseMessage] = []
    respuesta = POSTVENTA_FALLBACK
    try:
        modelo = ChatGoogleGenerativeAI(
            model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
            temperature=0,
            timeout=15,
            max_retries=1,
        )
        agente = create_agent(
            model=modelo,
            tools=POSTVENTA_TOOLS,
            system_prompt=POSTVENTA_PROMPT,
            checkpointer=False,
            name="agente_postventa",
        )
        # Mantener el hilo exterior hace que crear_reclamo reciba el thread_id
        # real sin exponerlo como un argumento que pueda elegir el modelo.
        with closing(
            agente.stream(
                {"messages": conversation},
                config={**config, "recursion_limit": 20},
                stream_mode="values",
            )
        ) as snapshots:
            for snapshot in snapshots:
                agent_messages = snapshot["messages"][len(conversation):]
        if agent_messages and agent_messages[-1].type == "ai":
            texto = agent_messages[-1].text.strip()
            if texto and not getattr(agent_messages[-1], "tool_calls", None):
                respuesta = "\n".join(texto.splitlines()[:4]).strip()
    except Exception as exc:
        logger.warning("No se pudo completar la postventa (%s).", type(exc).__name__)

    tools_used = [
        message.name for message in agent_messages
        if message.type == "tool" and message.name
    ]
    creados = [
        message.artifact for message in agent_messages
        if message.type == "tool"
        and message.name == "crear_reclamo"
        and isinstance(message.artifact, dict)
        and message.artifact.get("ticket")
    ]
    registros_no_confirmados = any(
        message.type == "tool"
        and message.name == "crear_reclamo"
        and not (
            isinstance(message.artifact, dict) and message.artifact.get("ticket")
        )
        for message in agent_messages
    )
    if creados:
        # No ocultar un ticket ya guardado aunque falle el último paso del modelo
        # o este lo omita al redactar su respuesta de hasta cuatro líneas.
        derivacion = any(item["motivo"] == "derivar a persona" for item in creados)
        plantilla = POSTVENTA_DERIVACION_CREADA if derivacion else POSTVENTA_RECLAMO_CREADO
        comprobante = plantilla.format(tickets=", ".join(item["ticket"] for item in creados))
        if respuesta == POSTVENTA_FALLBACK:
            respuesta = comprobante
        elif (
            any(item["ticket"] not in respuesta for item in creados)
            or (
                derivacion
                and POSTVENTA_AVISO_DERIVACION.casefold() not in respuesta.casefold()
            )
        ):
            respuesta = "\n".join([*respuesta.splitlines()[:3], comprobante])
        if registros_no_confirmados:
            respuesta = "\n".join([
                *respuesta.splitlines()[:2],
                comprobante,
                POSTVENTA_OTROS_RECLAMOS_NO_CONFIRMADOS,
            ])
    elif registros_no_confirmados:
        respuesta = POSTVENTA_RECLAMO_NO_CONFIRMADO

    # La memoria conversacional conserva usuario y respuesta, no un bucle ReAct
    # incompleto ni llamadas internas sin resolver si el modelo falla.
    update = _response_update(state, respuesta, "agente_postventa")
    update["saltos"] = [*state.get("saltos", []), "agente_postventa", *tools_used]
    return update


def respuesta_generica(state: RouterState) -> dict[str, object]:
    respuesta = GENERICA_FALLBACK
    try:
        tienda = TIENDA_PATH.read_text(encoding="utf-8")
        modelo = ChatGoogleGenerativeAI(
            model=os.getenv("MODELO", "gemini-3.5-flash-lite"),
            temperature=0,
            timeout=15,
            max_retries=1,
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
    return _response_update(state, respuesta, "respuesta_generica")


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


def build_diagram():
    """Expone el ciclo ReAct interno sin crear modelos, conexiones ni ejecutarlo."""
    diagram = build_graph().get_graph()
    for nombre, herramientas in (
        ("agente_preventa", PREVENTA_TOOLS),
        ("agente_postventa", POSTVENTA_TOOLS),
    ):
        agente = diagram.nodes[nombre]
        for herramienta in herramientas:
            nodo = diagram.add_node(herramienta, id=herramienta.name)
            diagram.add_edge(agente, nodo, conditional=True)
            diagram.add_edge(nodo, agente)
    return diagram
