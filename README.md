# agenticia26

## Ecommerce Router

Agente LangGraph y API FastAPI para clasificar mensajes de un chat de ecommerce en tres rutas: `preventa`, `postventa` y `generica`. Preventa consulta el catálogo y postventa atiende pedidos y reclamos mediante agentes ReAct; la ruta genérica conversa con el contexto de la tienda. El router usa Gemini con salida estructurada y conserva memoria por `user_id`/`thread_id`.

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
python main.py router "Busco un televisor" --hilo cliente1
```

`--saltos` imprime los nodos y el motivo del router; `--diagrama` muestra Mermaid sin invocar el modelo.

## Memoria persistente (Postgres)

Configura `DATABASE_URL` con la cadena de conexión de tu base Postgres, en `.env` para local y en **Settings → Config Vars** para Heroku. El valor de `.env.example` es ficticio; reemplázalo o deja `DATABASE_URL` vacía para usar RAM. Usa los parámetros SSL que indique tu proveedor (por ejemplo `?sslmode=require`). Nunca subas la cadena real a Git.

Al arrancar, la API abre un único pool asíncrono de **mínimo 1 y máximo 2 conexiones**, comprueba las conexiones antes de usarlas y ejecuta `setup()` para crear las tablas del checkpointer. Lo cierra al apagarse. La terminal usa `PostgresSaver` síncrono con los mismos límites y cierra su pool al terminar cada comando. El usuario de la base debe tener permiso para crear las tablas e índices de LangGraph.

Si falta la variable o falla la conexión/configuración inicial, la API registra el motivo y sigue en RAM. `GET /health` informa `"memoria": "postgres"` o `"memoria": "ram"`. La RAM **no persiste** entre procesos ni reinicios. El fallback solo se selecciona al arrancar: si se usó RAM por un fallo temporal, reinicia cuando Postgres esté disponible. Cada proceso tiene su propio pool; usa un único worker en Heroku para no multiplicar conexiones en una base compartida.

El `thread_id` de `/chat` sigue siendo `user_id`; en Telegram es `chat_id`. La terminal usa un hilo nuevo por defecto: usa `--hilo` para recuperar la misma conversación en ejecuciones distintas. Todos deben apuntar a la misma base para compartir memoria.

Prueba en dos procesos separados, con `DATABASE_URL` y `GOOGLE_API_KEY` válidas:

```powershell
python main.py router "me llamo Ana y busco un televisor de 55 pulgadas" --hilo prueba1
python main.py router "tengo hasta 500 mil pesos" --hilo prueba1
python scripts/ver_memoria.py prueba1
```

Para listar los hilos con su cantidad de checkpoints y la fecha del último:

```powershell
python scripts/ver_memoria.py
```

El visor no llama al modelo. Lee los mensajes del último checkpoint en su orden original (sin duplicarlos a partir de checkpoints previos). Sin Postgres informa que no puede acceder a la RAM de otros procesos. En una base compartida puede listar hilos de otros usuarios: ejecútalo solo si estás autorizado y no publiques su salida.

## Postventa y reclamos

Los ocho pedidos de ejemplo están en `data/pedidos.json` (números `4521` a `4528`) y las condiciones de devoluciones, cambios y garantía en `data/politicas.md`. Son datos inventados. Postventa recibe el historial, consulta esos archivos con herramientas y espera la confirmación del motivo antes de abrir un reclamo. `--saltos` incluye las herramientas utilizadas y `--diagrama` muestra los ciclos ReAct de ambas rutas sin invocarlas.

Al arrancar la API o la terminal se crea `reclamos` si no existe, en la misma `DATABASE_URL` del checkpointer. El usuario de la base necesita permisos de creación, inserción y lectura. Los reclamos incluyen ticket, número de pedido, motivo, detalle, `thread_id` y fecha UTC. Las escrituras abren y cierran una conexión adicional, como máximo una a la vez por proceso; no crean otro pool. El catálogo también puede usar una conexión adicional para sus consultas.

Si Postgres o la creación de la tabla no están disponibles al arrancar, los reclamos se guardan en RAM y el log lo advierte: no se comparten entre procesos y se pierden al reiniciar. No se escriben en archivos. Si una escritura falla después de arrancar con Postgres, se informa que no se pudo confirmar el registro, sin inventar un ticket ni reintentar automáticamente.

Para listar los reclamos persistidos, sin llamar al modelo:

```powershell
python scripts/ver_reclamos.py
python scripts/ver_reclamos.py --hilo cliente1
```

El visor no puede leer la RAM de otro proceso. Su salida contiene información de clientes: úsalo solo con autorización y no la publiques. Una derivación registra el ticket para atención humana; no envía por sí sola un aviso al equipo ni aprueba cambios o reembolsos.

## Levantar la API

```powershell
uvicorn api.app:app --reload --port 8000
```

### Interfaz web del chat

Abre <http://localhost:8000/> para usar la interfaz estilo WhatsApp (no necesita Node ni un servidor de frontend). Si el puerto está ocupado, ejecuta `python -m uvicorn api.app:app --reload --port 8001` y abre <http://localhost:8001/>.

- Pulsa **Acceso a la API** e introduce el valor de `API_KEY` de tu `.env`. La clave no se incluye en la página ni se guarda en `localStorage`, cookies o archivos: permanece en memoria en esa pestaña y hay que volver a introducirla al recargar.
- Escribe tu mensaje o elige una consulta sugerida. **Enter** envía; **Shift + Enter** añade una línea.
- **Ver saltos** muestra los nodos y herramientas que el grafo registró, su orden y el motivo de la ruta. El recorrido aparece **al terminar cada respuesta**, no en streaming. También puedes consultar el recorrido de una respuesta anterior desde su burbuja.
- El botón **+** inicia una conversación con un `thread_id` nuevo. La lista y las burbujas se conservan solo mientras la página está abierta; no recuperan visualmente historiales anteriores al recargar. La memoria del agente sigue usando Postgres o RAM según la configuración del servidor.
- La interfaz indica si la memoria activa es temporal (RAM). Sin `DATABASE_URL`, ni los mensajes del agente ni los reclamos sobreviven a un reinicio.

La interfaz se sirve desde `api/static/`. `POST /chat` mantiene la autenticación `X-API-Key` y ahora incluye `saltos` en su respuesta, además de `ruta`, `motivo` y `respuesta`.

Abre <http://localhost:8000/docs> y pulsa **Authorize** (el candado) para introducir tu clave y probar `/chat`. Ejemplo en PowerShell (usa la clave que configuraste):

```powershell
$apiKey = Read-Host "API_KEY"
curl.exe -X POST http://localhost:8000/chat -H "X-API-Key: $apiKey" -H "Content-Type: application/json" -d '{"user_id":"usuario-123","texto":"¿Tienen la polera azul en talla M?"}'
```

La API también tiene `GET /health`. El webhook `POST /telegram` acepta updates de texto, valida el secreto de Telegram y envía la respuesta por la Bot API.

## Clave de la API

`POST /chat` exige la cabecera `X-API-Key`. Si falta, es incorrecta o el servidor no tiene `API_KEY` configurada, responde **401** sin ejecutar el grafo. El body y la respuesta no cambian. `/health` sigue abierto y `/telegram` conserva su autenticación propia.

Genera una clave aleatoria desde el entorno virtual:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

En local, copia el resultado en `.env` como `API_KEY=<clave-generada>` y reinicia la API. Sustituye el valor ficticio de `.env.example`; no lo uses como clave real ni publiques tu `.env`.

En Heroku, abre **Settings → Config Vars → Reveal Config Vars** y añade `API_KEY` con la clave generada. También puedes configurarla mediante CLI:

```powershell
heroku config:set API_KEY="<clave-generada>" --app <nombre-de-tu-app-heroku>
```

Usa la misma clave en **Authorize** de `/docs` o en la cabecera `X-API-Key` de tu cliente (incluido Bruno). No la añadas a colecciones versionadas ni a código público.

## Pruebas

Las pruebas de autenticación y webhook no llaman al modelo ni a Telegram:

```powershell
pytest -q tests/test_api.py tests/test_telegram.py tests/test_memoria.py tests/test_ui.py
```

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
