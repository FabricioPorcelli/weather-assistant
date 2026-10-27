# Weather Assistant

Asistente conversacional que responde preguntas sobre el clima y da consejos
deterministas sobre paraguas, ropa, riego y actividades, usando datos reales de
[`weather-api`](../weather-api).

> Proyecto de portfolio. Se desarrolla por fases; este README describe el estado
> actual, no el producto terminado.

## Estado

**Fase 1 — Motor de consejos (sin IA)**

- [x] Aplicación FastAPI con configuración tipada.
- [x] `GET /v1/health`.
- [x] Cliente async de `weather-api` con timeouts, validación y errores de dominio.
- [x] Docker Compose con assistant + weather-api + Redis.
- [x] Consejos de paraguas, ropa y riego con reglas deterministas.
- [x] `GET /v1/advice/{kind}` con ciudad o coordenadas.
- [x] Errores de dominio traducidos a respuestas HTTP claras.
- [x] 114 tests sin red con `respx`.
- [ ] Actividades y mejor día (Fase 1B).
- [ ] Agente LLM (Fase 2).
- [ ] Chat con streaming SSE y persistencia (Fase 3).

## Qué hace por ahora

El servicio responde el chequeo de salud y tres consejos sin usar IA:

- **Paraguas:** sí, quizás o no, según probabilidad y lluvia prevista.
- **Ropa:** nivel de abrigo según temperatura, viento y amplitud térmica.
- **Riego:** sí, quizás o no, combinando las últimas 72 h de lluvia con las
  próximas 48 h de pronóstico.

El motor no inventa reglas: todas salen de umbrales configurables y tienen tests
que cubren sus bordes.

## Requisitos

- Python 3.13 para el contenedor.
- Docker y Docker Compose.
- El repo hermano `weather-api` clonado al lado de este, con su archivo `.env`
  conteniendo una API key válida de Visual Crossing.

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
| `ASSISTANT_CORS_ORIGINS` | vacío | Qué páginas web pueden llamar a la API desde el navegador (el dashboard usa el puerto 5500). |

El archivo `.env` está en `.gitignore`: nunca se versiona.

## Endpoints

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/v1/health` | Chequeo de vida, sin consultar `weather-api`. |
| GET | `/v1/advice/umbrella` | Consejo de paraguas. |
| GET | `/v1/advice/clothing` | Consejo de ropa y abrigo. |
| GET | `/v1/advice/watering` | Consejo de riego. |

Ubicación: una ciudad **o** un par de coordenadas, nunca ambas.

- `?city=Madrid`
- `?lat=-34.60&lon=-58.38&label=Buenos%20Aires`

Fecha opcional: `?date=YYYY-MM-DD`. Solo aplica a paraguas y ropa. El riego
siempre se calcula sobre “hoy” y las próximas 48 h; si se envía `date`, responde
`422`.

### Ejemplos

```bash
curl "http://localhost:8100/v1/advice/umbrella?city=Madrid"
curl "http://localhost:8100/v1/advice/clothing?city=Madrid"
curl "http://localhost:8100/v1/advice/clothing?city=Madrid&date=2026-10-29"
curl "http://localhost:8100/v1/advice/watering?city=Madrid"
curl "http://localhost:8100/v1/advice/umbrella?lat=-34.60&lon=-58.38&label=Buenos%20Aires"
```

Respuesta de ejemplo:

```json
{
  "kind": "umbrella",
  "verdict": "yes",
  "summary": "Probabilidad de precipitación de 70% y 2.0 mm: se recomienda paraguas.",
  "reasons": [
    {"metric": "precipitation_probability", "value": 70, "unit": "%"},
    {"metric": "precipitation_mm", "value": 2.0, "unit": "mm"}
  ],
  "target_date": "2026-10-27",
  "location_label": "Madrid, Spain",
  "data_sources": ["/v1/forecast"],
  "caveats": [
    "El pronóstico es diario: no distingue mañana, tarde o noche."
  ]
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

## Correr todo con Docker

```bash
docker compose up --build
```

- Assistant: http://localhost:8100
- Documentación interactiva: http://localhost:8100/docs
- Weather API: http://localhost:8000

El compose construye `weather-api` desde `../weather-api` y reutiliza su `.env`
para la API key. Redis queda solo dentro de la red de Docker, sin puerto
publicado.

> Si el compose propio de `weather-api` ya está corriendo, detenelo antes:
> ambos intentarían usar los puertos `8000` (API) y sus contenedores pueden
> chocar.

## Correr el asistente en modo desarrollo

Con `weather-api` ya disponible en `http://localhost:8000`:

```bash
conda create -n weather-assistant python=3.13 -y
conda activate weather-assistant
python -m pip install -r requirements.txt -r requirements-dev.txt
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
├── main.py              # app FastAPI, ciclo de vida, CORS y routers
├── config.py            # settings tipados desde variables de entorno
├── errors.py            # errores de dominio -> respuestas HTTP
├── api/
│   ├── health.py        # GET /v1/health
│   ├── advice.py        # GET /v1/advice/{kind}
│   └── dependencies.py  # ubicación y cliente HTTP inyectables
├── advice/
│   ├── models.py        # Advice, Reason, AdviceKind
│   ├── rules_config.py  # umbrales y niveles configurables
│   ├── errors.py        # errores propios del motor
│   ├── umbrella.py      # regla de paraguas
│   ├── clothing.py      # regla de ropa
│   ├── watering.py      # regla de riego
│   └── engine.py        # orquesta datos y reglas
└── clients/
    └── weather_api.py   # cliente HTTP, modelos y errores de dominio
tests/
├── conftest.py
├── helpers.py
├── test_advice_api.py
├── test_clothing.py
├── test_config.py
├── test_health.py
├── test_umbrella.py
├── test_watering.py
└── test_weather_api.py
```

## Decisiones de diseño

- **El LLM no decide, redacta.** Las reglas son funciones puras: reciben datos y
  devuelven un `Advice`. El modelo solo interpretará la pregunta y explicará el
  resultado en la Fase 2.
- **“Hoy” sale del pronóstico.** Se usa el primer día que devuelve `weather-api`,
  no el reloj de la computadora, para reducir problemas de zona horaria.
- **Los errores se traducen en la frontera.** El resto de la app no maneja
  códigos HTTP de `weather-api`: recibe errores con nombres claros
  (`LocationNotFound`, `RateLimited`, `UpstreamTimeout`, etc.).
- **Sin reintentos automáticos todavía.** Agregarlos sin medir primero puede
  empeorar el rate limit de `weather-api` (10 pedidos por minuto).
- **La salud es de vida, no de dependencias.** `/v1/health` no consulta a
  `weather-api` para no gastar rate limit ni acoplar los dos servicios.
