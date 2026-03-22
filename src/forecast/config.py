from __future__ import annotations

import os
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Forecast"
    environment: str = "development"
    frontend_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "postgresql+asyncpg://forecast:forecast@localhost:5432/forecast"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False
    specialist_agent_interval_minutes: int = 60
    endpoint_body_preview_chars: int = 300

    openai_api_key: SecretStr | None = None
    openai_chat_model: str = "gpt-4o"
    openai_embed_model: str = "text-embedding-3-small"
    openai_embed_dimensions: int = 384

    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = True
    langsmith_project: str = "forecast-dev"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_workspace_id: str | None = None
    langchain_callbacks_background: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return self.database_url

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.frontend_origins.split(",")
            if origin.strip()
        ]

    def configure_langsmith(self) -> None:
        os.environ["LANGSMITH_TRACING"] = "true" if self.langsmith_tracing else "false"
        os.environ["LANGSMITH_PROJECT"] = self.langsmith_project
        os.environ["LANGSMITH_ENDPOINT"] = self.langsmith_endpoint
        if self.langsmith_workspace_id:
            os.environ["LANGSMITH_WORKSPACE_ID"] = self.langsmith_workspace_id
        os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = (
            "true" if self.langchain_callbacks_background else "false"
        )
        if self.langsmith_api_key:
            os.environ["LANGSMITH_API_KEY"] = self.langsmith_api_key.get_secret_value()

    def openai_api_key_value(self) -> str:
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required to generate embeddings.")
        return self.openai_api_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
