FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg poppler-utils build-essential && rm -rf /var/lib/apt/lists/*
COPY . .
RUN pip install --no-cache-dir .
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --workers 1
