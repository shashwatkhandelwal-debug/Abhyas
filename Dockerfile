FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    poppler-utils \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Optimize layer caching: install python dependencies before copying application source
COPY pyproject.toml README.md ./
RUN mkdir -p backend content && touch backend/__init__.py content/__init__.py && pip install --no-cache-dir .

# Copy application source
COPY . .
RUN pip install --no-cache-dir --no-deps .

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Single-worker deploy per spec 12 §12.2; forwarded-allow-ips="*" for Render ingress proxy
CMD alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*" --workers 1
