"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.database import init_db
from src.orchestrator.orchestrator import orchestrator
from src.api.routes_orchestrator import router as orchestrator_router
from src.api.routes_ai_times import router as ai_times_router
from src.api.routes_mailman import router as mailman_router
from src.api.routes_wallstreet import router as wallstreet_router
from src.api.routes_docvault import router as docvault_router
from src.api.routes_custom import router as custom_router
from src.api.websocket import router as ws_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # Startup
    logger.info("Initializing database...")
    Path(settings.database_url.split("///")[-1]).parent.mkdir(parents=True, exist_ok=True)
    await init_db()

    logger.info("Starting orchestrator...")
    await orchestrator.startup()

    yield

    # Shutdown
    logger.info("Shutting down orchestrator...")
    await orchestrator.shutdown()


app = FastAPI(
    title="Multi-Agent Auto-Scheduling Platform",
    description="A locally-hosted multi-agent platform powered by Qwen3",
    version="1.0.0",
    lifespan=lifespan,
)

# Include API routers
app.include_router(orchestrator_router)
app.include_router(ai_times_router)
app.include_router(mailman_router)
app.include_router(wallstreet_router)
app.include_router(docvault_router)
app.include_router(custom_router)
app.include_router(ws_router)

# Serve frontend static files
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
