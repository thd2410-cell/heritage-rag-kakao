from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://heritage:heritage_dev_password@localhost:5432/heritage_rag"
    openai_api_key: str | None = None
    llm_provider: str = "openai"
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    embedding_model: str = "BAAI/bge-m3"
    khs_api_base: str = "http://www.khs.go.kr"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
