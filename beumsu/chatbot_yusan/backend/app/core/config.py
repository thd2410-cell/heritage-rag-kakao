from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    llm_provider: str = "dummy"
    embedding_provider: str = "mock"
    auto_confirm_entity_threshold: float = 0.86
    confirm_entity_threshold: float = 0.78
    default_top_k: int = 8

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
