# Ecommerce Router

Agente LangGraph y API FastAPI para clasificar mensajes de un chat de ecommerce en tres rutas: `preventa`, `postventa` y `generica`. La ruta de preventa y postventa responde con un agente cascarón; la respuesta genérica no usa el modelo. El router usa Gemini con salida estructurada y conserva memoria por `user_id`/`thread_id`.

## Requisitos y configuración local

Se requiere Python 3.12 y una clave de Google AI Studio para ejecutar clasificaciones reales.

En PowerShell, desde la raíz del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` y configura `GOOGLE_API_KEY`. `MODELO` usa `gemini-3.5-flash-lite` por defecto. No publiques `.env` ni incluyas claves reales en el código.

## Correr el router en local

Desde la raíz, con el entorno virtual activado:

```powershell
python main.py router "¿Tienen la polera azul en talla M?"
python main.py router "Mi pedido llegó roto" --saltos
python main.py router "hola" --diagrama
```

`--saltos` imprime los nodos y el motivo del router; `--diagrama` muestra Mermaid sin invocar el modelo.

## Levantar la API

```powershell
uvicorn api.app:app --reload --port 8000
```

Abre <http://localhost:8000/docs> para probar la API en Swagger. Ejemplo para `/chat`:

```powershell
curl.exe -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"user_id":"usuario-123","texto":"¿Tienen la polera azul en talla M?"}'
```

La API también tiene `GET /health`. El `POST /telegram` actual es solo un cascarón y aún no procesa ni verifica webhooks.

## Pruebas

Con `.env` configurado, ejecuta las 15 pruebas parametrizadas (exigen al menos 13 aciertos; llaman al modelo):

```powershell
pytest -q
```

Para ver una tabla con cada entrada, ruta esperada/obtenida y motivo:

```powershell
python scripts/test_router.py
```

Ambos comandos para el router real necesitan una `GOOGLE_API_KEY` válida y pueden realizar llamadas al modelo. Sin ella, los casos parametrizados de pytest se omiten.

## Desplegar en Heroku

El proyecto incluye `Procfile`, `.python-version` (`3.12`) y `requirements.txt`. Con Heroku CLI instalado, configura una aplicación (sustituye los valores de ejemplo; no escribas secretos reales en este README):

```powershell
heroku login
heroku create <nombre-unico-de-la-app>
heroku config:set GOOGLE_API_KEY=<tu-clave> MODELO=gemini-3.5-flash-lite TELEGRAM_TOKEN=<token-de-BotFather> TELEGRAM_SECRET=<secreto-aleatorio> PUBLIC_URL=https://<nombre-unico-de-la-app>.herokuapp.com
git push heroku main
heroku open
```

Si Heroku no es todavía un remoto Git, añádelo una vez con `heroku git:remote -a <nombre-unico-de-la-app>`. Verifica el despliegue en `https://<nombre-unico-de-la-app>.herokuapp.com/health` y abre `/docs`.

## Conectar Telegram

1. Crea el bot con BotFather y configura `TELEGRAM_TOKEN` en Heroku.
2. Despliega la app con una URL HTTPS pública y establece `PUBLIC_URL` con esa URL.
3. Cuando se complete la integración Telegram (el endpoint actual aún es un cascarón), registra el webhook con el token y secreto de tu entorno. En PowerShell:

```powershell
$token = "<token-de-BotFather>"
$publicUrl = "https://<nombre-unico-de-la-app>.herokuapp.com"
$secret = "<mismo-valor-de-TELEGRAM_SECRET>"
$body = @{ url = "$publicUrl/telegram"; secret_token = $secret } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$token/setWebhook" -ContentType "application/json" -Body $body
```

Telegram enviará el secreto en `X-Telegram-Bot-Api-Secret-Token`. **En esta versión `/telegram` todavía no valida ese header ni procesa actualizaciones**; completar esa lógica es necesario antes de usar el webhook en producción.
