from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_path: str = "./data/telemetry.db"
    redis_url: str = "redis://localhost:6379/0"
    ingest_api_keys: str = "dev-teammate-key-change-me"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "deepseek-r1:7b"
    job_queue_key: str = "sdth:translation_jobs"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def api_keys(self) -> set[str]:
        return {k.strip() for k in self.ingest_api_keys.split(",") if k.strip()}


settings = Settings()
