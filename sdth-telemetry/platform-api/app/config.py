from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _first_existing(*candidates: Path, fallback: str) -> str:
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return fallback


def _default_datasets_dir() -> str:
    here = Path(__file__).resolve()
    searched = [parent / "raw_telemetry-datasets" for parent in here.parents]
    return _first_existing(*searched, fallback="/datasets")


def _default_replay_dir() -> str:
    here = Path(__file__).resolve()
    searched = [parent / "sdth-replay" / "public" for parent in here.parents]
    return _first_existing(*searched, Path("/replay/public"), fallback="/replay/public")


def _default_demo_dir() -> str:
    here = Path(__file__).resolve()
    searched = [parent / "sdth-demo" for parent in here.parents]
    return _first_existing(*searched, fallback="/demo")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: str = "./data/telemetry.db"
    redis_url: str = "redis://localhost:6379/0"
    ingest_api_keys: str = "dev-key-12345"
    # Defaults target a plain local Ollama install. host.docker.internal only
    # resolves from inside a container, so whenever the API ran directly on the
    # host the model was unreachable and the AI-analysis panel sat permanently
    # on its offline fallback. qwen2.5:7b-instruct follows the JSON output
    # format reliably while staying fast enough for a live demo; deepseek-r1:7b
    # remains selectable via OLLAMA_MODEL.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    warm_local_model: bool = True
    auto_start_local_model: bool = False
    local_demo_worker: bool = False
    ingest_model_enrichment: bool = True
    demo_analysis_timeout_seconds: float = 120.0
    job_queue_key: str = "sdth:translation_jobs"
    raw_upload_queue_key: str = "sdth:raw_uploads"
    raw_upload_dir: str = "./data/raw-uploads"
    visuals_dir: str = "./data/visuals"
    reports_dir: str = "./data/reports"
    tile_cache_dir: str = "./data/tiles"
    raw_upload_max_bytes: int = 100 * 1024 * 1024
    raw_datasets_dir: str = Field(default_factory=_default_datasets_dir)
    replay_static_dir: str = Field(default_factory=_default_replay_dir)
    demo_static_dir: str = Field(default_factory=_default_demo_dir)
    redact_operator_location: bool = True
    retention_days: int = 30
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def api_keys(self) -> set[str]:
        return {k.strip() for k in self.ingest_api_keys.split(",") if k.strip()}


settings = Settings()
