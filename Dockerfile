FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    poppler-utils \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Optimize layer caching: install python dependencies before copying application source
COPY pyproject.toml README.md ./
RUN mkdir -p backend content eval && touch backend/__init__.py content/__init__.py eval/__init__.py && pip install --no-cache-dir .

# Copy application source
COPY . .
RUN pip install --no-cache-dir --no-deps .

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Migrate, optionally seed (SEED_ON_BOOT), then single-worker uvicorn; see scripts/start.sh
CMD ["sh", "scripts/start.sh"]
