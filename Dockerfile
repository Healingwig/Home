FROM python:3.12-slim

# ffmpeg recomprime el vídeo antes de mandarlo al modelo y, cuando hace falta,
# extrae fotogramas y audio.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/tmp/recetas \
    PORT=8000

WORKDIR /srv

COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Extras opcionales (ver requirements-*.txt). Descomenta y reconstruye.
# RUN pip install --no-cache-dir -r requirements-whisper.txt
# RUN pip install --no-cache-dir -r requirements-anthropic.txt

COPY app ./app

EXPOSE 8000

# $PORT lo fija Cloud Run; en local se queda en 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
