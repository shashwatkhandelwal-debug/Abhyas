FROM python:3.11-slim

WORKDIR /app

# Install system dependencies: ffmpeg (audio), poppler-utils (pdftoppm for OCR ingest)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    poppler-utils \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy application source
COPY . .

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Single-worker deploy per spec 12 §12.2
CMD alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --workers 1
