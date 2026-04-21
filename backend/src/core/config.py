from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.dev", extra="ignore")

    postgres_user: str
    postgres_password: str
    postgres_host: str
    pgport: int = Field(alias="PGPORT")
    postgres_db: str

    celery_broker_url: str = "redis://backend-redis:6379/0"

    storage_dir: Path = Path(__file__).resolve().parent.parent.parent / "storage" / "files"
    upload_chunk_size: int = 1024 * 1024

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.pgport}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
