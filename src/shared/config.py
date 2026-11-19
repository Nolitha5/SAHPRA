"""
Application settings for the Container Closure Agent S6 project.

Values are read from environment variables prefixed S6_, or from a
.env file in the project root. Nothing here invents an M1/M2/M3/M4b
integration contract -- these are only our own local settings
(database location, local Ollama endpoint).
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="S6_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Path to the shared SQLite audit database file. Relative paths
    # are resolved against the current working directory at the
    # point create_write_engine()/create_readonly_engine() is called.
    database_path: str = Field(default="data/audit.db")

    # Local Ollama instance used by the S.6 agent's evaluator (Phase
    # 2+, not used by Phase 1). Not validated against a real instance
    # here -- this is only where the value lives.
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3")


def get_settings() -> Settings:
    """Factory rather than a module-level singleton, so tests can
    construct Settings with overrides without mutating global state."""
    return Settings()
