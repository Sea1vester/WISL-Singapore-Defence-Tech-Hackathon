from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.demo_api import router as demo_router
from app.db import run_migrations
from app.analytics import router as analytics_router
from app.census_api import router as census_router
from app.datasets import router as datasets_router
from app.incident_api import router as incident_router
from app.ingest import router as ingest_router
from app.mission_library import router as mission_library_router
from app.preflight_report_api import router as preflight_report_router
from app.query import router as query_router
from app.tiles import router as tiles_router
from app.visual_api import router as visual_router

# Uvicorn only configures its own loggers; give the app/worker loggers a
# stderr handler so per-stage ingest lines reach the console terminal too.
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

logger = logging.getLogger("sdth")


def _warm_local_model() -> None:
    """Preload the demo model into Ollama so the first analysis call skips load."""
    import threading

    def _ping() -> None:
        try:
            from app.demo_api import prepare_default_model

            result = prepare_default_model()
            if result.get("warmed"):
                logger.info("Warmed local model %s", settings.ollama_model)
            else:
                logger.warning("Local model startup: %s", result.get("message", result["status"]))
        except Exception:  # noqa: BLE001 - warmup is best-effort only
            pass

    threading.Thread(target=_ping, daemon=True).start()


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    if settings.warm_local_model:
        _warm_local_model()
    if settings.local_demo_worker:
        from app.local_worker import recover, stop
        recover()
    try:
        yield
    finally:
        if settings.local_demo_worker:
            stop()


app = FastAPI(
    title="SDTH Telemetry Platform",
    description=(
        "Ingest drone logs, parse them into deterministic canonical JSON, "
        "index incidents, and serve Cesium replay. Ollama is optional enrichment only."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
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
app.include_router(preflight_report_router)
app.include_router(demo_router)
app.include_router(mission_library_router)
app.include_router(tiles_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/demo/", status_code=307)


@app.middleware("http")
async def send_standalone_replay_to_console(request: Request, call_next):
    path = request.url.path
    if path in {"/replay", "/replay/", "/replay/index.html"} and request.query_params.get("embed") != "1":
        return RedirectResponse(url="/demo/", status_code=307)
    return await call_next(request)


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


_demo_dir = Path(settings.demo_static_dir)
if (_demo_dir / "index.html").is_file():
    app.mount("/demo", StaticFiles(directory=_demo_dir, html=True), name="demo")
    logger.info("Serving WISL console from %s", _demo_dir)
else:
    logger.warning("WISL console missing at %s; /demo will 404", _demo_dir)


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
