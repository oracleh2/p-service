from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Настройки приложения"""

    # Database
    database_url: str = "postgresql://proxy_user:proxy_password@postgres:5432/mobile_proxy"
    database_pool_size: int = 20
    database_max_overflow: int = 30

    # Redis
    redis_url: str = "redis://redis:6379"
    redis_pool_size: int = 10

    # Security
    secret_key: str = "your-secret-key-change-in-production"
    jwt_secret_key: str = "your-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    jwt_expiration_minutes: int = 30
    api_key_length: int = 32

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    proxy_host: str = "0.0.0.0"
    proxy_port: int = 8080

    # Proxy settings
    default_rotation_interval: int = 600  # 10 minutes
    max_devices: int = 50
    max_requests_per_minute: int = 100
    request_timeout: int = 30
    request_timeout_seconds: int = 30
    max_concurrent_connections: int = 100
    buffer_size: int = 8192

    # Monitoring
    health_check_interval: int = 30
    heartbeat_timeout: int = 60
    log_retention_days: int = 30
    metrics_retention_days: int = 90

    # Rotation Settings
    max_rotation_attempts: int = 3
    rotation_timeout_seconds: int = 60
    rotation_retry_delay_seconds: int = 10

    # External Services (optional)
    telegram_bot_token: Optional[str] = ""
    slack_webhook_url: Optional[str] = ""

    # Celery
    celery_broker_url: str = "redis://localhost:6379"
    celery_result_backend: str = "redis://localhost:6379"

    # Development
    debug: bool = False
    reload: bool = False
    log_level: str = "INFO"

    # API Info
    api_v1_str: str = "/api/v1"
    project_name: str = "Mobile Proxy Service"
    project_version: str = "1.0.0"

    # CORS
    cors_origins: list = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://frontend:3000",
        "http://192.168.1.50:3000"
    ]

    class Config:
        env_file = ".env"
        case_sensitive = False
        # Разрешаем дополнительные поля из .env
        extra = "allow"


# Создаем глобальный экземпляр настроек
settings = Settings()


def get_settings() -> Settings:
    return settings


# Настройки по умолчанию для системы
DEFAULT_SYSTEM_CONFIG = {
    "rotation_interval": {
        "value": "600",
        "description": "Интервал автоматической ротации IP в секундах",
        "config_type": "integer"
    },
    "auto_rotation_enabled": {
        "value": "true",
        "description": "Включить автоматическую ротацию IP",
        "config_type": "boolean"
    },
    "max_devices": {
        "value": "50",
        "description": "Максимальное количество устройств",
        "config_type": "integer"
    },
    "requests_per_minute_limit": {
        "value": "100",
        "description": "Лимит запросов в минуту на устройство",
        "config_type": "integer"
    },
    "heartbeat_timeout": {
        "value": "60",
        "description": "Таймаут heartbeat в секундах",
        "config_type": "integer"
    },
    "rotation_timeout": {
        "value": "60",
        "description": "Таймаут ротации IP в секундах",
        "config_type": "integer"
    },
    "log_retention_days": {
        "value": "30",
        "description": "Количество дней хранения логов",
        "config_type": "integer"
    },
    "enable_alerts": {
        "value": "true",
        "description": "Включить уведомления об ошибках",
        "config_type": "boolean"
    },
    "alert_success_rate_threshold": {
        "value": "85",
        "description": "Порог успешности запросов для алертов (%)",
        "config_type": "integer"
    },
    "device_offline_alert_minutes": {
        "value": "5",
        "description": "Время офлайн устройства для алерта (минуты)",
        "config_type": "integer"
    }
}

# Константы для совместимости
PROXY_HOST = settings.proxy_host
PROXY_PORT = settings.proxy_port
MAX_CONCURRENT_CONNECTIONS = settings.max_concurrent_connections
REQUEST_TIMEOUT_SECONDS = settings.request_timeout_seconds
BUFFER_SIZE = settings.buffer_size
DEFAULT_ROTATION_INTERVAL = settings.default_rotation_interval
MAX_ROTATION_ATTEMPTS = settings.max_rotation_attempts
ROTATION_TIMEOUT_SECONDS = settings.rotation_timeout_seconds
ROTATION_RETRY_DELAY_SECONDS = settings.rotation_retry_delay_seconds
MAX_DEVICES = settings.max_devices
MAX_REQUESTS_PER_MINUTE = settings.max_requests_per_minute
HEALTH_CHECK_INTERVAL = settings.health_check_interval
HEARTBEAT_TIMEOUT = settings.heartbeat_timeout
LOG_RETENTION_DAYS = settings.log_retention_days
