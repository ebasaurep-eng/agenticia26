import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from src.router.graph import graph


CASOS_PATH = Path(__file__).with_name("casos_router.json")
CASOS = json.loads(CASOS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def aciertos_router(request):
    aciertos = []

    def comprobar_umbral():
        if aciertos:
            assert sum(aciertos) >= 13, (
                f"El router acertó {sum(aciertos)}/15; se requieren al menos 13."
            )

    request.addfinalizer(comprobar_umbral)
    return aciertos


@pytest.mark.parametrize("caso", CASOS, ids=lambda caso: caso["mensaje"])
def test_router_clasifica_al_menos_13_de_15(caso, aciertos_router):
    if not os.getenv("GOOGLE_API_KEY"):
        pytest.skip("Configura GOOGLE_API_KEY en .env para ejecutar el router real")

    resultado = graph.invoke(
        {"messages": [HumanMessage(content=caso["mensaje"])]},
        config={"configurable": {"thread_id": str(uuid4())}},
    )
    aciertos_router.append(resultado["ruta"] == caso["esperado"])
