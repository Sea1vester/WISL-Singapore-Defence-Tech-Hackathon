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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: str = "./data/telemetry.db"
    redis_url: str = "redis://localhost:6379/0"
    ingest_api_keys: str = "dev-teammate-key-change-me"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "deepseek-r1:7b"
    job_queue_key: str = "sdth:translation_jobs"
    raw_upload_queue_key: str = "sdth:raw_uploads"
    raw_upload_dir: str = "./data/raw-uploads"
    raw_upload_max_bytes: int = 100 * 1024 * 1024
    raw_datasets_dir: str = Field(default_factory=_default_datasets_dir)
    replay_static_dir: str = Field(default_factory=_default_replay_dir)
    redact_operator_location: bool = True
    retention_days: int = 30
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def api_keys(self) -> set[str]:
        return {k.strip() for k in self.ingest_api_keys.split(",") if k.strip()}


settings = Settings()
