# Reglas del proyecto

- Los agentes van en `src/{nombre_agente}/` con `graph.py`, `prompts.py` y `tools.py`.
- Cada nodo debe tener su propio prompt en `prompts.py`. No incluir reglas ni prompts dentro de `graph.py`.
- Los agentes se ejecutan desde la raíz con `python main.py {nombre_agente} "mensaje"`.
- `--saltos` imprime los nodos por los que pasó el grafo.
- `--diagrama` imprime el Mermaid del grafo sin ejecutarlo.
- `--hilo NOMBRE` elige el `thread_id`; API y terminal usan Postgres si `DATABASE_URL` está disponible y RAM como fallback.
- La API va en `api/app.py` (FastAPI) y se levanta con `uvicorn api.app:app --reload --port 8000`.
- Los scripts sueltos van en `scripts/` y las pruebas en `tests/` (pytest).
- Para Heroku: mantener `Procfile` con `web: uvicorn api.app:app --host 0.0.0.0 --port $PORT`, `.python-version` con `3.12` y `requirements.txt` siempre actualizado.
- `.gitignore` debe ignorar `.env`, `.venv`, `__pycache__` y `.langgraph_api`.
