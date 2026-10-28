# Weather Assistant

Asistente de clima con API HTTP, agente LLM y chat con streaming. Consulta
[weather-api](https://github.com/FabricioPorcelli/weather-api) y aplica reglas
deterministas para paraguas, ropa, riego y actividades.

## Repos relacionados

El proyecto se compone de tres repos que se complementan:

- [weather-api](https://github.com/FabricioPorcelli/weather-api): obtiene y
  normaliza los datos de clima.
- [weather-dashboard](https://github.com/FabricioPorcelli/weather-dashboard):
  muestra el mapa, el clima y el chat.
- weather-assistant: este repo. Contiene el motor de consejos, el agente LLM y
  la API de chat.

El dashboard consulta `weather-api` para el clima y `weather-assistant` para el
chat. El assistant consulta `weather-api` para resolver consejos y actividades.

## Qué hace

- Devuelve consejos de paraguas, ropa y riego para una ciudad o coordenadas.
- Evalúa actividades al aire libre y calcula el mejor día de un rango.
- Expone los consejos por HTTP sin LLM.
- Ejecuta un agente con tool calling desde la terminal.
- Ofrece chat con SSE, sesiones e historial persistido.
- Ajusta el consejo de ropa con feedback de comodidad.
- Integra el chat en `weather-dashboard` de forma opcional.

## Requisitos

- Python 3.13.
- Docker y Docker Compose.
- El repo [weather-api](https://github.com/FabricioPorcelli/weather-api) en
  `../weather-api`, con su `.env` y una clave de Visual Crossing.
- Una clave de Groq para ejecutar el agente real. Los tests no la necesitan.

## Configuración

```bash
cp .env.example .env
```

Variables principales:

| Variable | Default |
|---|---|
| `WEATHER_API_BASE_URL` | `http://localhost:8000` |
| `WEATHER_API_TIMEOUT_SECONDS` | `10` |
| `WEATHER_API_RETRIES` | `1` |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` |
| `LLM_API_KEY` | vacío |
| `LLM_MODEL` | `openai/gpt-oss-120b` |
| `DATABASE_URL` | `postgresql+asyncpg://assistant:assistant@localhost:5432/assistant` |
| `REDIS_URL` | `redis://localhost:6379/1` |
| `ASSISTANT_CORS_ORIGINS` | `http://localhost:5500,http://127.0.0.1:5500` |
| `RATE_LIMIT` | `20/minute` |
| `MAX_MESSAGE_CHARS` | `500` |
| `HISTORY_TURNS` | `6` |

El resto está documentado en `.env.example`.

## Docker

```bash
docker compose up --build
```

Servicios:

- Assistant: `http://localhost:8100`
- Documentación de la API: `http://localhost:8100/docs`
- Weather API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`

El compose construye [weather-api](https://github.com/FabricioPorcelli/weather-api)
desde `../weather-api` y reutiliza su `.env`. El contenedor del assistant ejecuta
`alembic upgrade head` antes de Uvicorn.

Si el compose de `weather-api` ya está corriendo, hay que detenerlo antes para
liberar el puerto `8000`.

## Desarrollo local

Con `weather-api` disponible en `http://localhost:8000`:

```bash
conda create -n weather-assistant python=3.13 -y
conda activate weather-assistant
python -m pip install -r requirements.txt -r requirements-dev.txt

docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload --port 8100
```

## Endpoints

| Método | Endpoint |
|---|---|
| GET | `/v1/health` |
| GET | `/v1/advice/umbrella` |
| GET | `/v1/advice/clothing` |
| GET | `/v1/advice/watering` |
| GET | `/v1/activities/{activity}/evaluate` |
| GET | `/v1/activities/{activity}/best-day` |
| POST | `/v1/chat` |
| POST | `/v1/feedback` |

Los endpoints de consejos y actividades aceptan `city` o `lat` y `lon`.

```text
?city=Madrid
?lat=-34.60&lon=-58.38&label=Buenos%20Aires
```

`date` es opcional para paraguas y ropa, y obligatorio para `evaluate`. El riego
siempre usa la fecha actual. `best-day` requiere `start`, `end` y acepta `top`
entre 1 y 15.

### Ejemplos

```bash
curl "http://localhost:8100/v1/advice/umbrella?city=Madrid"
curl "http://localhost:8100/v1/advice/clothing?city=Madrid&date=$(date -d tomorrow +%F)"
curl "http://localhost:8100/v1/advice/watering?city=Madrid"

curl "http://localhost:8100/v1/activities/outdoor_event/evaluate?city=Madrid&date=$(date +%F)"
curl "http://localhost:8100/v1/activities/exterior_painting/best-day?city=Madrid&start=$(date +%F)&end=$(date -d '+6 days' +%F)&top=3"
```

## Consejos

### Paraguas

- `precipitation_probability >= 50` o `precipitation_mm >= 1.0`: `yes`.
- `precipitation_probability >= 25` o `precipitation_mm >= 0.2`: `maybe`.
- Caso contrario: `no`.

### Ropa

Niveles: muy liviana, liviana, capa intermedia, campera, abrigo con bufanda y
abrigo grueso.

- Hoy usa `feels_like_c` de `/v1/weather`.
- Días futuros usan el promedio de máxima y mínima.
- Viento desde 30 km/h suma un nivel de abrigo.
- Amplitud térmica desde 10 °C sugiere una capa extra.
- Paraguas `yes` sugiere impermeable.

### Riego

- Lluvia acumulada de 72 h desde 10 mm: `no`.
- Lluvia prevista en 48 h con probabilidad desde 60 % y desde 5 mm: `no`.
- Máxima desde 30 °C y lluvia de 72 h menor a 2 mm: `yes`.
- Máxima desde 20 °C y lluvia de 72 h menor a 5 mm: `maybe`.
- Caso contrario: `no`.

Las 72 h son los tres días anteriores a hoy. Las 48 h son hoy y mañana. Es una
heurística, no un balance hídrico.

## Actividades

Actividades disponibles: `outdoor_event`, `outdoor_exercise`,
`exterior_painting` y `drying_laundry`.

Cada día parte de 100 puntos. Un veto lo deja en 0. El veredicto es `ideal`
desde 80, `acceptable` desde 50 y `not_recommended` por debajo de 50.

| Actividad | Vetos | Penalizaciones |
|---|---|---|
| `outdoor_event` | prob. ≥ 40, mm ≥ 1, viento ≥ 35 | prob. 20-39: -20; viento 20-34,9: -20; fuera de 18-28 °C: -5 por °C |
| `outdoor_exercise` | prob. ≥ 60, mm ≥ 5, viento ≥ 40, máxima ≥ 33 °C | prob. 20-59: -15; fuera de 10-22 °C: -5 por °C |
| `exterior_painting` | prob. ≥ 30, mm ≥ 0,2, viento ≥ 25, lluvia del día anterior ≥ 1 mm | siguiente día con prob. ≥ 40: -20; fuera de 15-28 °C: -5 por °C |
| `drying_laundry` | prob. ≥ 40, mm ≥ 1 | máxima fuera de 20-32 °C: -5 por °C; viento fuera de 10-30 km/h: -15 |

La penalización por temperatura tiene un tope de 60 puntos.

- Días 1 a 3: `high`; días 4 a 7: `medium`; desde el día 8: `low`.
- El rango se recorta al horizonte de 15 días y el recorte aparece en `caveats`.
- Si no queda ningún día, responde `422`.
- El ranking ordena por puntaje y desempata por fecha.
- `has_acceptable_day` considera todos los días evaluados.

Para pintura exterior, la lluvia del día anterior se lee del histórico si el día
evaluado es hoy y del pronóstico si es futuro.

## Caché

Cada request usa un cliente con caché temporal para clima, pronóstico e
histórico. La caché se descarta al terminar el request.

## CLI

```bash
conda activate weather-assistant
python -m app.cli "¿Llevo paraguas en Madrid?"
python -m app.cli "¿Cuál es el mejor día de esta semana para pintar el frente en Córdoba?"
python -m app.cli "¿Dónde conviene hacer un asado el finde, Mar del Plata o Pinamar?"
```

El CLI usa hasta 4 herramientas por pregunta, valida sus argumentos con Pydantic
y comparte la caché durante el turno. No guarda historial.

## Chat

```bash
curl -N -X POST http://localhost:8100/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"¿Llevo paraguas en Madrid?","location":{"city":"Madrid"}}'
```

Body:

```json
{
  "session_id": "opcional",
  "user_id": "opcional",
  "message": "¿Llevo paraguas en Madrid?",
  "location": { "city": "Madrid", "label": "Madrid" }
}
```

Eventos SSE:

| Evento | Contenido |
|---|---|
| `session` | `session_id` creado o reutilizado |
| `tool_call` | Nombre de la herramienta |
| `advice` | Datos del motor con `kind` |
| `token` | Fragmento de texto |
| `done` | Fin del turno |
| `error` | Error controlado |

Sin `session_id` se crea una sesión. El historial enviado al LLM son los últimos
`HISTORY_TURNS` pares usuario/asistente.

`EventSource` solo permite GET. El dashboard usa `fetch` y `ReadableStream` para
consumir este SSE por POST.

## Feedback de ropa

El endpoint de feedback ajusta un offset por usuario anónimo:

```bash
curl -X POST http://localhost:8100/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{"user_id":"00000000-0000-0000-0000-000000000001","feedback":"cold"}'
```

Valores de `feedback`: `cold`, `just_right` y `hot`.

- `cold` resta 0.5 °C a la temperatura de referencia.
- `hot` suma 0.5 °C.
- `just_right` no cambia el offset.
- El offset queda entre -10 y 10 °C.

El offset se aplica solo al consejo de ropa. No hay login: el dashboard genera un
UUID anónimo y lo guarda en `localStorage`.

Metodología: actualización incremental con paso de 0.5 °C y límite de ±10 °C. La
simulación de `tests/test_personalization.py` muestra que el offset converge al
valor objetivo con feedback consistente.

Limitaciones: no modela actividad, hora del día ni otras preferencias. Si se
borra `localStorage`, el navegador obtiene otro UUID y pierde el ajuste anterior.

## Dashboard

[weather-dashboard](https://github.com/FabricioPorcelli/weather-dashboard)
consume el chat de forma opcional. Si el assistant está apagado, el clima y el
pronóstico siguen funcionando.

El chat se abre en un popup sobre el marcador, muestra texto y confianza, y
guarda las conversaciones en el navegador. Cambiar de punto a más de 5 km inicia
una conversación nueva. Los puntos usados permiten retomarla.

Después de un consejo de ropa aparecen tres botones de feedback. El navegador
guarda un UUID anónimo y lo envía con el chat y con el feedback.

## Base de datos

Tablas: `sessions`, `messages`, `tool_calls` y `user_preferences`.

```bash
alembic upgrade head
```

Producción usa PostgreSQL 16. Los tests usan SQLite async.

## Evals

`evals/cases.yaml` contiene 60 casos. Los fixtures de `evals/fixtures/` simulan
`weather-api`.

```bash
python evals/run_evals.py --models openai/gpt-oss-120b --delay-seconds 4
```

El runner mide selección de herramientas, argumentos, veredicto, mejor fecha,
menciones, groundedness, latencia p50/p95, tokens y costo.

La cuota de Groq no permite ejecutar los 60 casos en una corrida. El reporte
publicado usa 11 casos representativos.

| Modelo | Casos | Pass rate | Groundedness | p50 | p95 | Tokens | Costo USD |
|---|---|---|---|---|---|---|---|
| `openai/gpt-oss-120b` | 11 | 1.0 | 1.0 | 7891.91 ms | 12493.99 ms | 47755 | 0.008533 |

Reportes: `evals/reports/`.

## Observabilidad

Cada request agrega `X-Request-ID` y registra una línea JSON con método, ruta,
estado y duración. No se guardan mensajes, ubicaciones, argumentos de
herramientas ni claves.

## Tests

```bash
pytest -q
ruff check .
ruff format --check .
```

313 tests. No requieren red, Docker ni claves: `respx` simula las respuestas HTTP.

## Estructura

```text
app/
├── main.py
├── cli.py
├── config.py
├── errors.py
├── limiter.py
├── api/
│   ├── health.py
│   ├── advice.py
│   ├── activities.py
│   ├── chat.py
│   ├── feedback.py
│   └── dependencies.py
├── advice/
├── agent/
├── chat/
├── clients/
├── db/
└── observability/
evals/
├── cases.yaml
├── fixtures/
├── run_evals.py
└── reports/
migrations/
tests/
```

## Notas

- `/v1/health` no consulta `weather-api`.
- Los reintentos de `weather-api` solo cubren `502`, `504` y timeouts.
- Los errores de `weather-api` se traducen a errores de dominio.
- El chat persiste mensajes y tool calls en PostgreSQL.
- El feedback de ropa se guarda por UUID anónimo en `user_preferences`.
- Los workflows de GitHub Actions ejecutan lint y tests. Los evals usan
  `workflow_dispatch` y el secreto `GROQ_API_KEY`.
