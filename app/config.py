import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # FastAPI настройки
    app_title: str = "Telegram Auth Bot"
    app_version: str = "1.0.0"
    app_host: str = Field(default="0.0.0.0", env="APP_HOST")
    app_port: int = Field(default=8000, env="APP_PORT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Telegram Bot настройки
    bot_token: str = Field(env="BOT_TOKEN")
    webhook_url: str = Field(env="WEBHOOK_URL")
    webhook_path: str = Field(default="/webhook/telegram", env="WEBHOOK_PATH")
    
    # PostgreSQL настройки
    postgres_host: str = Field(env="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")
    postgres_db: str = Field(env="POSTGRES_DB")
    postgres_user: str = Field(env="POSTGRES_USER")
    postgres_password: str = Field(env="POSTGRES_PASSWORD")
    
    # Redis настройки
    redis_host: str = Field(env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_db: int = Field(default=0, env="REDIS_DB")
    
    # Настройки авторизации
    api_secret_key: str = Field(env="API_SECRET_KEY")
    auth_request_timeout: int = Field(default=300, env="AUTH_REQUEST_TIMEOUT")  # 5 минут
    max_pending_requests: int = Field(default=5, env="MAX_PENDING_REQUESTS")
    
    # PgAdmin настройки
    pgadmin_email: Optional[str] = Field(default="admin@admin.com", env="PGADMIN_EMAIL")
    pgadmin_password: Optional[str] = Field(default="admin", env="PGADMIN_PASSWORD")
    
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def full_webhook_url(self) -> str:
        return f"{self.webhook_url.rstrip('/')}{self.webhook_path}"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
