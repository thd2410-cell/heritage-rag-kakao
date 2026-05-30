from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_provider: str = "dummy"
    embedding_provider: str = "mock"
    embedding_dimensions: int = 1536
    vector_search_limit: int = 80
    auto_confirm_entity_threshold: float = 0.86
    confirm_entity_threshold: float = 0.78
    default_top_k: int = 8

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
