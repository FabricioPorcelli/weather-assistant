# Weather Assistant

Asistente conversacional que responde preguntas sobre el clima y da consejos
deterministas sobre paraguas, ropa, riego y actividades, usando datos reales de
[`weather-api`](../weather-api).

> Proyecto de portfolio. Se desarrolla por fases; este README describe el estado
> actual, no el producto terminado.

## Estado

**Fase 0 — Base del proyecto**

- [x] Aplicación FastAPI con configuración tipada.
- [x] `GET /v1/health`.
- [x] Cliente async de `weather-api` con timeouts, validación y errores de dominio.
- [x] Docker Compose con assistant + weather-api + Redis.
- [x] Tests sin red con `respx`.
- [ ] Motor de consejos (Fase 1).
- [ ] Agente LLM (Fase 2).
- [ ] Chat con streaming SSE y persistencia (Fase 3).

## Qué hace por ahora

El servicio arranca, responde el chequeo de salud y tiene listo el cliente que
consultará `weather-api`. Todavía no expone consejos ni chat: eso llega en las
siguientes fases.

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

Variables de esta fase:

| Variable | Default | Para qué sirve |
|---|---|---|
| `WEATHER_API_BASE_URL` | `http://localhost:8000` | Dónde está `weather-api` cuando corrés el asistente sin Docker. |
| `WEATHER_API_TIMEOUT_SECONDS` | `10` | Cuánto esperar una respuesta antes de considerarla caída. |
| `ASSISTANT_CORS_ORIGINS` | vacío | Qué páginas web pueden llamar a la API desde el navegador (el dashboard usa el puerto 5500). |

El archivo `.env` está en `.gitignore`: nunca se versiona.

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
├── main.py          # app FastAPI, ciclo de vida, CORS y routers
├── config.py        # settings tipados desde variables de entorno
├── api/
│   └── health.py    # GET /v1/health
└── clients/
    └── weather_api.py  # cliente HTTP, modelos y errores de dominio
tests/
├── conftest.py
├── test_config.py
├── test_health.py
└── test_weather_api.py
```

## Decisiones de diseño

- **El LLM no decide, redacta.** Las reglas de consejo serán deterministas y
  testeables; el modelo solo interpretará la pregunta y explicará el resultado.
- **Los errores se traducen en la frontera.** El resto de la app no maneja
  códigos HTTP de `weather-api`: recibe errores con nombres claros
  (`LocationNotFound`, `RateLimited`, `UpstreamTimeout`, etc.).
- **Sin reintentos automáticos todavía.** Agregarlos sin medir primero puede
  empeorar el rate limit de `weather-api` (10 pedidos por minuto).
- **La salud es de vida, no de dependencias.** `/v1/health` no consulta a
  `weather-api` para no gastar rate limit ni acoplar los dos servicios.
