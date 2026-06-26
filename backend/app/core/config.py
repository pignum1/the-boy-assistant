from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/dbname"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM API Keys
    OPENAI_API_KEY: str = ""
    CLAUDE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GLM_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # Encryption
    ENCRYPTION_KEY: str = ""

    # Workspace
    WORKSPACE_BASE_PATH: str = "~/the-boy-workspaces"

    # RAG / Embedding
    SILICONFLOW_API_KEY: str = ""
    RERANKER_URL: str = ""
    RERANKER_API_KEY: str = ""
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # App
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Auth — 不设置则跳过认证（开发模式）
    API_KEY: str = ""

    # 速率限制（每分钟请求数，默认 120）
    RATE_LIMIT_RPM: int = 120

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
