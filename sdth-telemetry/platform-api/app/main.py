from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import run_migrations
from app.analytics import router as analytics_router
from app.census_api import router as census_router
from app.datasets import router as datasets_router
from app.incident_api import router as incident_router
from app.ingest import router as ingest_router
from app.query import router as query_router
from app.visual_api import router as visual_router

logger = logging.getLogger("sdth")


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    yield


app = FastAPI(
    title="SDTH Telemetry Platform",
    description=(
        "Ingest drone logs, parse them into deterministic canonical JSON, "
        "index incidents, and serve Cesium replay. Ollama is optional enrichment only."
    ),
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

app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(analytics_router)
app.include_router(incident_router)
app.include_router(datasets_router)
app.include_router(visual_router)
app.include_router(census_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _mount_replay() -> None:
    replay_dir = Path(settings.replay_static_dir)
    if not replay_dir.is_dir():
        logger.warning("Replay static dir missing at %s; /replay will 404", replay_dir)
        return
    lib_dir = replay_dir.parent / "src"
    if lib_dir.is_dir():
        app.mount("/replay/lib", StaticFiles(directory=lib_dir), name="replay-lib")
    app.mount("/replay", StaticFiles(directory=replay_dir, html=True), name="replay")
    logger.info("Serving Cesium replay from %s", replay_dir)


_mount_replay()


def main() -> None:
    import uvicorn

    from app.config import settings

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
