"""FastAPI application entrypoint for Abhyas backend (§1)."""

import importlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.auth.router import router as auth_router
from backend.app.config import settings
from backend.app.jobs.admin_api import router as jobs_admin_router
from backend.app.jobs.scheduler import start_scheduler
from backend.app.web import STATIC_DIR, admin_router, chat_router, teacher_router
from backend.app.whatsapp.router import router as whatsapp_router

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("abhyas")


async def _cleanup_clients() -> None:
    """Closes shared singletons (Anthropic and speech HTTP clients) if initialized."""
    try:
        llm_mod = importlib.import_module("backend.app.llm.client")
        close_anthropic = getattr(llm_mod, "close_anthropic_client", None)
        if callable(close_anthropic):
            res = close_anthropic()
            if hasattr(res, "__await__"):
                await res
    except Exception as e:
        logger.debug("LLM client cleanup skipped: %s", e)

    try:
        speech_mod = importlib.import_module("backend.app.speech.client")
        close_speech = getattr(speech_mod, "close_speech_http_client", None)
        if callable(close_speech):
            res = close_speech()
            if hasattr(res, "__await__"):
                await res
    except Exception as e:
        logger.debug("Speech client cleanup skipped: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting Abhyas Backend (Env: %s)", settings.ENVIRONMENT)
    scheduler = start_scheduler()
    yield
    logger.info("Shutting down Abhyas Backend")
    if scheduler is not None and getattr(scheduler, "running", False):
        try:
            scheduler.shutdown(wait=False)
        except RuntimeError as e:
            logger.debug("Scheduler shutdown error: %s", e)
    await _cleanup_clients()


app = FastAPI(
    title="Abhyas API",
    description="A voice-first WhatsApp practice partner for government primary FLN teachers",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.PUBLIC_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount Routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(teacher_router)
app.include_router(whatsapp_router)
app.include_router(jobs_admin_router)
app.include_router(admin_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect root to login page (spec/12)."""
    return RedirectResponse(url="/login", status_code=303)


@app.get("/healthz", tags=["System"])
async def healthz() -> dict[str, str]:
    """Lightweight liveness probe returning status and git SHA (spec/12)."""
    return {"status": "ok", "git_sha": settings.GIT_SHA}


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for service monitoring."""
    return {
        "status": "healthy",
        "service": "abhyas-backend",
        "environment": settings.ENVIRONMENT,
    }
