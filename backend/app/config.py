# backend/app/config.py
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Настройки приложения"""

    # Database
    database_url: str = "postgresql://proxy_user:proxy_password@postgres:5432/mobile_proxy"

    # Redis
    redis_url: str = "redis://redis:6379"

    # Security
    secret_key: str = "your-secret-key-change-in-production"
    jwt_secret_key: str = "your-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    proxy_port: int = 8080

    # Proxy settings
    default_rotation_interval: int = 600  # 10 minutes
    max_devices: int = 50
    max_requests_per_minute: int = 100
    request_timeout: int = 30

    # Monitoring
    health_check_interval: int = 30
    heartbeat_timeout: int = 60
    log_retention_days: int = 30

    # Development
    debug: bool = False
    reload: bool = False

    log_level: str = "INFO"
    api_v1_str: str = "/api/v1"
    project_name: str = "Mobile Proxy Service"
    project_version: str = "1.0.0"

    # CORS
    cors_origins: list = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://frontend:3000"
    ]

    class Config:
        env_file = ".env"
        case_sensitive = False


# Создаем глобальный экземпляр настроек
settings = Settings()
