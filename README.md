# agenticia26

## Ecommerce Router

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

La API también tiene `GET /health`. El webhook `POST /telegram` acepta updates de texto, valida el secreto de Telegram y envía la respuesta por la Bot API.

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
heroku config:set GOOGLE_API_KEY=<tu-clave> MODELO=gemini-3.5-flash-lite
git push heroku main
heroku open
```

Si Heroku no es todavía un remoto Git, añádelo una vez con `heroku git:remote -a <nombre-unico-de-la-app>`. Verifica el despliegue en `https://<nombre-unico-de-la-app>.herokuapp.com/health` y abre `/docs`.

## Telegram

La integración usa solo `httpx`, sin librerías de bot. El webhook valida `X-Telegram-Bot-Api-Secret-Token`, toma `message.chat.id` y `message.text`, ejecuta el grafo con `chat_id` como `thread_id` y responde con `sendMessage`. Los updates sin texto se ignoran. No pongas el token del bot en el código ni en Git.

### Pasos de despliegue y verificación

1. Crea el bot con `@BotFather` usando `/newbot`. Copia el token y elige un secreto propio (no uses el valor de ejemplo `cambiame`). Configúralos en Heroku:

   ```powershell
   $app = "<nombre-de-tu-app-heroku>"
   heroku config:set --app $app TELEGRAM_TOKEN="<token-de-BotFather>" TELEGRAM_SECRET="<secreto-aleatorio>" PUBLIC_URL="https://<nombre-de-tu-app-heroku>.herokuapp.com"
   ```

2. Desde la raíz del repositorio, commitea y despliega los cambios a GitHub y Heroku:

   ```powershell
   git add api/app.py scripts/set_webhook.py scripts/webhook_info.py README.md
   git commit -m "Conecta webhook de Telegram"
   git push origin main
   git push heroku main
   ```

   Si todavía no configuraste el remoto de Heroku: `heroku git:remote -a <nombre-de-tu-app-heroku>`.

3. En tu `.env` local, configura `TELEGRAM_TOKEN`, el mismo `TELEGRAM_SECRET` y `PUBLIC_URL=https://<nombre-de-tu-app-heroku>.herokuapp.com`. Registra y comprueba el webhook:

   ```powershell
   python scripts/set_webhook.py
   python scripts/webhook_info.py
   ```

   El segundo comando comprueba la URL esperada, los updates pendientes y el último error de Telegram.

4. Abre otra terminal y sigue los logs; después envía estos seis mensajes al bot y comprueba la ruta que registra el router:

   ```powershell
   heroku logs --tail --app $app
   ```

   - `¿tienen la polera azul en talla M?` → `preventa`
   - `mi pedido 4521 llegó roto` → `postventa`
   - `hola` → `generica`
   - `¿cuánto cuesta el envío a Valparaíso?` → `preventa`
   - `quiero devolver unas zapatillas` → `postventa`
   - `¿qué hora es en Tokio?` → `generica`

5. Si el bot no responde, comprueba que `/telegram` esté disponible por HTTPS, que `TELEGRAM_SECRET` en Heroku coincida con el secreto usado al registrar el webhook, que `TELEGRAM_TOKEN` sea el de ese bot y que `python scripts/webhook_info.py` no reporte errores pendientes. Revisa también `heroku logs --tail --app $app`.

### Prueba local opcional

Con la API local levantada en el puerto 8000, puedes exponerla temporalmente con Cloudflare Tunnel:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Usa la URL HTTPS que imprime `cloudflared` como `PUBLIC_URL` en `.env` y ejecuta los dos scripts de webhook anteriores. Mantén la API ejecutándose mientras pruebas.
