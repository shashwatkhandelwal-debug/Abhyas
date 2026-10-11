"""FastAPI application entrypoint for Abhyas backend (§1)."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.whatsapp.router import router as whatsapp_router

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("abhyas")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Abhyas Backend (Env: %s)", settings.ENVIRONMENT)
    yield
    logger.info("Shutting down Abhyas Backend")


app = FastAPI(
    title="Abhyas API",
    description="A voice-first WhatsApp practice partner for government primary FLN teachers",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(whatsapp_router)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for service monitoring."""
    return {
        "status": "healthy",
        "service": "abhyas-backend",
        "environment": settings.ENVIRONMENT,
    }
