# Imagen base: Python 3.13 liviano, misma versión menor que el proyecto.
FROM python:3.13-slim

WORKDIR /app

# Logs sin buffer y sin archivos .pyc dentro del contenedor.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# tzdata permite que TZ funcione dentro del contenedor.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Las dependencias se copian primero para aprovechar la caché de capas de Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

EXPOSE 8100

# 0.0.0.0 permite recibir conexiones desde fuera del contenedor.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
