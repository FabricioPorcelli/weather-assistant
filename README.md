# Weather Assistant

Asistente conversacional que responde preguntas sobre el clima y da consejos
deterministas sobre paraguas, ropa, riego y actividades, usando datos reales de
[`weather-api`](../weather-api).

> Proyecto de portfolio. Se desarrolla por fases; este README describe el estado
> actual, no el producto terminado.

## Estado

**Fase 4 — Integración con el dashboard**

- [x] Aplicación FastAPI con configuración tipada.
- [x] `GET /v1/health`.
- [x] Cliente async de `weather-api` con timeouts, validación y errores de dominio.
- [x] Docker Compose con assistant + weather-api + PostgreSQL + Redis.
- [x] Consejos de paraguas, ropa y riego con reglas deterministas.
- [x] Evaluación de actividades y ranking del mejor día.
- [x] Endpoints de consejos y actividades con ciudad o coordenadas.
- [x] Caché en memoria durante un mismo pedido.
- [x] Agente con tool calling implementado a mano.
- [x] Cliente LLM compatible con OpenAI Chat Completions.
- [x] CLI: `python -m app.cli "¿Llevo paraguas en Madrid?"`.
- [x] `POST /v1/chat` con streaming SSE real.
- [x] Sesiones, historial y tool calls persistidos en PostgreSQL.
- [x] Rate limit por IP y límites de mensaje.
- [x] Dashboard con chat opcional en ventana emergente, texto natural y confianza.
- [x] 289 tests sin red con `respx`.

## Qué hace por ahora

El servicio responde sin usar IA:

- **Paraguas:** sí, quizás o no, según probabilidad y lluvia prevista.
- **Ropa:** nivel de abrigo según temperatura, viento y amplitud térmica.
- **Riego:** sí, quizás o no, combinando las últimas 72 h de lluvia con las
  próximas 48 h de pronóstico.
- **Actividades:** evalúa un día o busca el mejor día de un rango para un asado,
  ejercicio, pintura exterior o tender ropa.
- **Agente en CLI:** interpreta la pregunta, elige herramientas, valida sus
  argumentos y redacta la respuesta final.
- **Chat SSE:** el mismo agente por HTTP, con respuesta en streaming, sesiones e
  historial persistido.

El motor no inventa reglas: todas salen de umbrales configurables y tienen tests
que cubren sus bordes. El LLM no calcula consejos: solo interpreta y redacta.

## Requisitos

- Python 3.13 para el contenedor.
- Docker y Docker Compose.
- El repo hermano `weather-api` clonado al lado de este, con su archivo `.env`
  conteniendo una API key válida de Visual Crossing.
- Una API key de Groq para probar el agente real. Los tests no la necesitan.
- PostgreSQL 16 y Redis. Docker Compose los levanta automáticamente.

La estructura esperada es:

```
Documents/
├── weather-api/
├── weather-dashboard/
└── weather-assistant/   ← este repo
```

## Configuración

Copiar el archivo de ejemplo:

```bash
cp .env.example .env
```

Variables actuales:

| Variable | Default | Para qué sirve |
|---|---|---|
| `WEATHER_API_BASE_URL` | `http://localhost:8000` | Dónde está `weather-api` cuando corrés el asistente sin Docker. |
| `WEATHER_API_TIMEOUT_SECONDS` | `10` | Cuánto esperar una respuesta antes de considerarla caída. |
| `WEATHER_API_RETRIES` | `1` | Reintentos ante `502`, `504` o timeout transitorio. |
| `WEATHER_API_RETRY_DELAY_SECONDS` | `0.5` | Espera entre reintentos. |
| `ASSISTANT_CORS_ORIGINS` | vacío | Qué páginas web pueden llamar a la API desde el navegador (el dashboard usa el puerto 5500). |
| `LLM_BASE_URL` | vacío | URL base del proveedor compatible con OpenAI. |
| `LLM_API_KEY` | vacío | Clave del proveedor. Nunca se versiona. |
| `LLM_MODEL` | vacío | Modelo que soporta tool calling. |
| `LLM_TIMEOUT_SECONDS` | `30` | Tiempo máximo de espera del LLM. |
| `MAX_TOOL_CALLS_PER_TURN` | `4` | Herramientas máximas por pregunta. |
| `DATABASE_URL` | PostgreSQL local | Conexión a la base de datos. |
| `REDIS_URL` | `redis://localhost:6379/1` | Almacenamiento del rate limit. |
| `RATE_LIMIT` | `20/minute` | Límite de pedidos por IP. |
| `MAX_MESSAGE_CHARS` | `500` | Largo máximo del mensaje de chat. |
| `HISTORY_TURNS` | `6` | Pares usuario/asistente que se envían al LLM. |

El archivo `.env` está en `.gitignore`: nunca se versiona.

### Configurar Groq

El `.env` ya viene preparado para Groq con `openai/gpt-oss-120b`. Solo falta
completar la clave:

```env
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=tu_clave_de_groq
LLM_MODEL=openai/gpt-oss-120b
```

### Alternativa OpenCode

El `.env` también tiene comentadas las variables para usar la API de OpenCode:

```env
LLM_BASE_URL=https://opencode.ai/inference/openai/v1
LLM_API_KEY=tu_clave_oficial_de_opencode
LLM_MODEL=deepseek-v4.1-flash
```

Solo funciona si tu cuenta permite usar el modelo desde clientes externos. El
código no cambia: es el mismo cliente compatible con OpenAI.

## Endpoints

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/v1/health` | Chequeo de vida, sin consultar `weather-api`. |
| GET | `/v1/advice/umbrella` | Consejo de paraguas. |
| GET | `/v1/advice/clothing` | Consejo de ropa y abrigo. |
| GET | `/v1/advice/watering` | Consejo de riego. |
| GET | `/v1/activities/{activity}/evaluate` | Evalúa una actividad en un día. |
| GET | `/v1/activities/{activity}/best-day` | Ranking de mejores días en un rango. |
| POST | `/v1/chat` | Chat con streaming SSE, sesiones e historial. |

Ubicación: una ciudad **o** un par de coordenadas, nunca ambas.

- `?city=Madrid`
- `?lat=-34.60&lon=-58.38&label=Buenos%20Aires`

Consejos: `date` es opcional para paraguas y ropa. El riego siempre se calcula
sobre “hoy” y las próximas 48 h; si se envía `date`, responde `422`.

Actividades disponibles:

- `outdoor_event`
- `outdoor_exercise`
- `exterior_painting`
- `drying_laundry`

Para `evaluate`, `date` es obligatorio. Para `best-day`, `start` y `end` son
obligatorios y `top` va de 1 a 15 (default 3).

### Ejemplos

```bash
curl "http://localhost:8100/v1/advice/umbrella?city=Madrid"
curl "http://localhost:8100/v1/advice/clothing?city=Madrid"
curl "http://localhost:8100/v1/advice/clothing?city=Madrid&date=2026-10-29"
curl "http://localhost:8100/v1/advice/watering?city=Madrid"

curl "http://localhost:8100/v1/activities/outdoor_event/evaluate?city=Madrid&date=$(date +%F)"
curl "http://localhost:8100/v1/activities/exterior_painting/best-day?city=Madrid&start=$(date +%F)&end=$(date -d '+6 days' +%F)&top=3"
curl "http://localhost:8100/v1/activities/drying_laundry/best-day?city=Madrid&start=$(date +%F)&end=$(date -d '+6 days' +%F)"
```

Respuesta de ejemplo de una evaluación:

```json
{
  "date": "2026-10-27",
  "score": 80,
  "verdict": "ideal",
  "reasons": [
    {"metric": "average_temperature_c", "value": 23.0, "unit": "°C"},
    {"metric": "precipitation_probability", "value": 25, "unit": "%"},
    {"metric": "precipitation_mm", "value": 0.0, "unit": "mm"},
    {"metric": "wind_speed_kmh", "value": 10.0, "unit": "km/h"}
  ],
  "blockers": [],
  "confidence": "high"
}
```

## Reglas implementadas

### Paraguas

- `precipitation_probability >= 50` **o** `precipitation_mm >= 1.0` → `yes`.
- `precipitation_probability >= 25` **o** `precipitation_mm >= 0.2` → `maybe`.
- Caso contrario → `no`.

### Ropa

Niveles por temperatura de referencia: muy liviana, liviana, capa intermedia,
campera, abrigo con bufanda y abrigo grueso.

- Si el día es hoy, se usa `feels_like_c` de `/v1/weather`.
- Si es un día futuro, se usa el promedio de máxima y mínima del pronóstico.
- Viento `>= 30 km/h` suma un nivel de abrigo y sugiere cortaviento.
- Amplitud térmica `>= 10 °C` sugiere una capa extra.
- Si el paraguas da `yes`, sugiere impermeable.

### Riego

- Lluvia acumulada de las últimas 72 h `>= 10 mm` → `no`.
- Lluvia prevista en las próximas 48 h con probabilidad `>= 60%` y `>= 5 mm` →
  `no`, conviene esperar.
- Máxima `>= 30 °C` y lluvia de 72 h `< 2 mm` → `yes`.
- Máxima `>= 20 °C` y lluvia de 72 h `< 5 mm` → `maybe`.
- Caso contrario → `no`.

Interpretación usada para las ventanas de tiempo:

- “Últimas 72 h”: los 3 días completos anteriores a hoy, leídos del histórico.
- “Próximas 48 h”: hoy y mañana del pronóstico.

El consejo de riego es una heurística y no un balance hídrico real; la
evapotranspiración sería más exacta.

### Actividades

Cada día empieza con 100 puntos. Un veto lo deja en 0. El veredicto es `ideal`
desde 80, `acceptable` desde 50 y `not_recommended` por debajo de 50.

| Actividad | Vetos | Penalizaciones |
|---|---|---|
| `outdoor_event` | prob. ≥ 40, mm ≥ 1, viento ≥ 35 | prob. 20–39: −20; viento 20–34,9: −20; fuera de 18–28 °C: −5 por °C |
| `outdoor_exercise` | prob. ≥ 60, mm ≥ 5, viento ≥ 40, máxima ≥ 33 °C | prob. 20–59: −15; fuera de 10–22 °C: −5 por °C |
| `exterior_painting` | prob. ≥ 30, mm ≥ 0,2, viento ≥ 25, lluvia del día anterior ≥ 1 mm | siguiente día con prob. ≥ 40: −20; fuera de 15–28 °C: −5 por °C |
| `drying_laundry` | prob. ≥ 40, mm ≥ 1 | máxima fuera de 20–32 °C: −5 por °C; viento fuera de 10–30 km/h: −15 |

La penalización por temperatura tiene un tope de −60 puntos.

Detalles de confianza y rango:

- Días 1–3: `high`; días 4–7: `medium`; desde el día 8: `low`.
- El rango se recorta al horizonte de 15 días y el recorte se informa en
  `caveats`.
- Si no queda ningún día del rango dentro del pronóstico, responde `422`.
- El ranking ordena por puntaje y, en empate, primero la fecha más cercana.
- `has_acceptable_day` mira todos los días evaluados, no solo los del `top`.

Para pintura exterior, la humedad de la superficie se aproxima con la lluvia del
día anterior. Si el día evaluado es hoy, se consulta el histórico de ayer; si es
futuro, se usa el día anterior del pronóstico.

## Caché por pedido

Cada pedido HTTP usa un envoltorio con memoria temporal. Si durante ese pedido se
repiten el mismo pronóstico, histórico o clima actual, se reutiliza la respuesta.
Al terminar el pedido, la memoria se descarta: no se mezclan datos entre pedidos.

## Agente en CLI

Con `weather-api` disponible en `http://localhost:8000` y la clave del LLM en
`.env`:

```bash
conda activate weather-assistant
python -m app.cli "¿Llevo paraguas en Madrid?"
python -m app.cli "¿Cuál es el mejor día de esta semana para pintar el frente en Córdoba?"
python -m app.cli "¿Dónde conviene ir el finde, Mar del Plata o Pinamar?"
```

El agente:

- Lee la fecha actual y la inyecta en el prompt.
- Puede llamar hasta 4 herramientas por pregunta.
- Valida todos los argumentos con Pydantic antes de ejecutarlos.
- Comparte la caché de `weather-api` entre las herramientas de esa pregunta.
- Devuelve los errores de herramientas al modelo para que pueda corregir o
  explicar el problema.
- Incluye `date_label` con el día de la semana ya formateado para evitar que el
  modelo lo calcule mal.
- No usa streaming: imprime la respuesta final cuando termina.

Proveedor actual: Groq con `openai/gpt-oss-120b`. El cliente es compatible con
OpenAI Chat Completions, así que se puede cambiar de proveedor solo con
variables de entorno.

## Chat con streaming SSE

`POST /v1/chat` recibe:

```json
{
  "session_id": "opcional",
  "message": "¿Llevo paraguas en Madrid?",
  "location": { "city": "Madrid", "label": "Madrid" }
}
```

Ejemplo con `curl`:

```bash
curl -N -X POST http://localhost:8100/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"¿Llevo paraguas en Madrid?","location":{"city":"Madrid"}}'
```

Eventos:

| Evento | Contenido |
|---|---|
| `session` | `session_id` creado o reutilizado. |
| `tool_call` | Nombre de la herramienta que se está ejecutando. |
| `advice` | Tarjeta con `kind`: `umbrella`, `clothing`, `watering`, `activity` o `best_day`. |
| `token` | Fragmento de texto de la respuesta. |
| `done` | Fin del turno. |
| `error` | Error controlado durante el stream. |

Si no se envía `session_id`, se crea una sesión nueva. Para continuar una
conversación, se envía el `session_id` recibido. El historial de los últimos
`HISTORY_TURNS` pares usuario/asistente se agrega al prompt.

> `EventSource` del navegador solo permite GET. El dashboard usa `fetch` +
> `ReadableStream` para consumir este SSE por POST.

## Integración con el dashboard

El repo hermano `weather-dashboard` consume este chat de forma **opcional**:

- El chat se abre en un popup de Leaflet anclado al marcador, con el título
  “Pregunta sobre el clima”.
- Si el assistant está corriendo, permite preguntar y muestra solo la respuesta
  en lenguaje natural, con una línea de confianza al final.
- Si el assistant está apagado, el dashboard de clima sigue funcionando y solo
  falla esa ventana, con un mensaje controlado.
- Las negritas `**texto**` se renderizan de forma segura.
- Si el punto cambia a más de 5 km, el chat reinicia la conversación. Los puntos
  usados y sus mensajes quedan guardados en el navegador; al volver a ese punto
  o tocar el ancla se restaura la conversación.
- El origen del dashboard (`http://localhost:5500` y `http://127.0.0.1:5500`)
  está permitido por `ASSISTANT_CORS_ORIGINS`.

## Base de datos y migraciones

Tablas:

- `sessions`: conversación, fechas y última ubicación mostrada.
- `messages`: mensajes de usuario y asistente.
- `tool_calls`: auditoría de herramientas, argumentos y resultados.

Las credenciales locales son usuario `assistant`, contraseña `assistant` y base
`assistant`.

Aplicar migraciones:

```bash
alembic upgrade head
```

En Docker, el contenedor ejecuta `alembic upgrade head` antes de arrancar.
Los tests usan SQLite async para no depender de Docker; producción usa
PostgreSQL 16.

## Correr todo con Docker

```bash
docker compose up --build
```

- Assistant: http://localhost:8100
- Documentación interactiva: http://localhost:8100/docs
- Weather API: http://localhost:8000

El compose construye `weather-api` desde `../weather-api` y reutiliza su `.env`
para la API key. También levanta PostgreSQL y Redis. PostgreSQL queda accesible
en `localhost:5432` para desarrollo local. El assistant usa
`TZ=America/Argentina/Buenos_Aires` para que la fecha del prompt coincida con la
hora local.

> Si el compose propio de `weather-api` ya está corriendo, detenelo antes:
> ambos intentarían usar los puertos `8000` (API) y sus contenedores pueden
> chocar.

## Correr el asistente en modo desarrollo

Con `weather-api` ya disponible en `http://localhost:8000`:

```bash
conda create -n weather-assistant python=3.13 -y
conda activate weather-assistant
python -m pip install -r requirements.txt -r requirements-dev.txt

# Levantá PostgreSQL y Redis desde el compose.
docker compose up -d postgres redis

alembic upgrade head
uvicorn app.main:app --reload --port 8100
```

## Probar

```bash
curl http://localhost:8100/v1/health
```

```json
{"status":"ok","service":"weather-assistant","version":"0.1.0"}
```

Tests y lint:

```bash
pytest -q
ruff check .
ruff format --check .
```

Los tests no necesitan red, Docker ni una API key: `respx` intercepta las
llamadas HTTP y devuelve respuestas preparadas.

## Estructura

```
app/
├── main.py              # app FastAPI, ciclo de vida, CORS, limiter y routers
├── cli.py               # entrada python -m app.cli
├── config.py            # settings tipados desde variables de entorno
├── errors.py            # errores de dominio -> respuestas HTTP
├── limiter.py           # rate limit con slowapi y Redis
├── api/
│   ├── health.py        # GET /v1/health
│   ├── advice.py        # GET /v1/advice/{kind}
│   ├── activities.py    # endpoints de actividades
│   ├── chat.py          # POST /v1/chat
│   └── dependencies.py  # ubicación, cliente HTTP y LLM inyectables
├── advice/
│   ├── models.py        # Advice, DayEvaluation, BestDayResult
│   ├── rules_config.py  # umbrales y niveles configurables
│   ├── errors.py        # errores propios del motor
│   ├── umbrella.py      # regla de paraguas
│   ├── clothing.py      # regla de ropa
│   ├── watering.py      # regla de riego
│   ├── activities.py    # perfiles, vetos y puntaje
│   ├── best_day.py      # recorte de rango y ranking
│   └── engine.py        # orquesta datos y reglas
├── agent/
│   ├── llm.py           # LLMClient, Chat Completions y streaming
│   ├── tools.py         # esquemas, validación y ejecución
│   ├── prompts.py       # system prompt con fecha y reglas
│   ├── messages.py      # formato de mensajes assistant/tool
│   ├── loop.py          # loop de tool calling para CLI
│   └── streaming.py     # loop con streaming para el chat
├── chat/
│   └── service.py       # sesiones, historial, SSE y persistencia
├── db/
│   ├── models.py        # sessions, messages y tool_calls
│   ├── session.py       # engine y sesiones async
│   └── repositories.py  # consultas de persistencia
└── clients/
    ├── weather_api.py   # cliente HTTP, modelos y errores de dominio
    └── request_cache.py # caché temporal por pedido
migrations/
├── env.py
└── versions/0001_initial.py
tests/
├── conftest.py
├── helpers.py
├── fakes.py
├── test_activities.py
├── test_activities_api.py
├── test_advice_api.py
├── test_agent_loop.py
├── test_best_day.py
├── test_chat_api.py
├── test_chat_repository.py
├── test_cli.py
├── test_clothing.py
├── test_config.py
├── test_health.py
├── test_llm_client.py
├── test_llm_streaming.py
├── test_prompt.py
├── test_request_cache.py
├── test_streaming_agent.py
├── test_tools.py
├── test_umbrella.py
├── test_watering.py
├── test_weather_api.py
└── test_weather_api_retries.py
```

## Decisiones de diseño

- **El LLM no decide, redacta.** Las reglas son funciones puras: reciben datos y
  devuelven un resultado. El modelo solo interpreta la pregunta y explica el
  resultado.
- **“Hoy” sale del pronóstico.** Se usa el primer día que devuelve `weather-api`,
  no el reloj de la computadora, para reducir problemas de zona horaria.
- **Los errores se traducen en la frontera.** El resto de la app no maneja
  códigos HTTP de `weather-api`: recibe errores con nombres claros
  (`LocationNotFound`, `RateLimited`, `UpstreamTimeout`, etc.).
- **Caché por pedido, no global.** Se ahorra rate limit sin mezclar usuarios ni
  conservar datos viejos indefinidamente.
- **El agente usa Chat Completions directamente.** No usamos SDK ni frameworks
  de agentes: el loop de tool calling está implementado a mano con `httpx`.
- **Máximo 4 herramientas por pregunta.** Cada llamada cuenta, incluso si la
  herramienta devuelve un error.
- **Tests sin LLM real.** `FakeLLMClient` devuelve respuestas guionadas y permite
  probar el loop de forma determinista.
- **Streaming real.** El chat usa `stream: true` de Chat Completions y reenvía
  cada fragmento de texto como evento SSE.
- **PostgreSQL en producción, SQLite en tests.** PostgreSQL soporta concurrencia
  y es la base real; SQLite permite tests rápidos, aislados y sin Docker. Los
  tipos elegidos (`Uuid`, `JSON`, fechas) funcionan en ambos.
- **La sesión guarda solo lo necesario.** El LLM recibe los últimos pares
  usuario/asistente; las herramientas quedan en `tool_calls` para auditoría.
- **Rate limit con slowapi.** Los contadores van a Redis y, si falla, slowapi
  cae a memoria para no tumbar la API.
- **Reintento corto solo para fallos transitorios.** Un `502`, `504` o timeout
  se reintenta una vez tras una espera breve. Un `404` o `429` no se reintenta:
  repetirlo no ayuda y puede empeorar el rate limit.
- **La salud es de vida, no de dependencias.** `/v1/health` no consulta a
  `weather-api` para no gastar rate limit ni acoplar los dos servicios.
