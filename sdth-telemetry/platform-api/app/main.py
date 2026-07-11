from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import run_migrations
from app.ingest import router as ingest_router
from app.query import router as query_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    yield


app = FastAPI(
    title="SDTH Telemetry Platform",
    description="Ingest normalized drone telemetry, store in SQLite, translate via Ollama.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ingest_router)
app.include_router(query_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
