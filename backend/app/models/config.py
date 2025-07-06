from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # API
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Mobile Proxy Service"
    PROJECT_VERSION: str = "1.0.0"

    # Database
    DATABASE_URL: str = "postgresql://proxy_user:proxy_password@localhost:5432/mobile_proxy"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 30

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_POOL_SIZE: int = 10

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_SECRET_KEY: str = "your-jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 30
    API_KEY_LENGTH: int = 32

    # Server Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    PROXY_HOST: str = "0.0.0.0"
    PROXY_PORT: int = 8080

    # Proxy Settings
    DEFAULT_ROTATION_INTERVAL: int = 600  # 10 минут по умолчанию
    MAX_DEVICES: int = 50
    MAX_REQUESTS_PER_MINUTE: int = 100
    REQUEST_TIMEOUT_SECONDS: int = 30
    MAX_CONCURRENT_CONNECTIONS: int = 100
    BUFFER_SIZE: int = 8192

    # Monitoring
    HEALTH_CHECK_INTERVAL: int = 30
    HEARTBEAT_TIMEOUT: int = 60
    LOG_RETENTION_DAYS: int = 30
    METRICS_RETENTION_DAYS: int = 90
    LOG_LEVEL: str = "INFO"

    # Rotation Settings
    MAX_ROTATION_ATTEMPTS: int = 3
    ROTATION_TIMEOUT_SECONDS: int = 60
    ROTATION_RETRY_DELAY_SECONDS: int = 10

    # External Services (optional)
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    SLACK_WEBHOOK_URL: Optional[str] = None

    # Development
    DEBUG: bool = False
    RELOAD: bool = False

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


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
PROXY_HOST = settings.PROXY_HOST
PROXY_PORT = settings.PROXY_PORT
MAX_CONCURRENT_CONNECTIONS = settings.MAX_CONCURRENT_CONNECTIONS
REQUEST_TIMEOUT_SECONDS = settings.REQUEST_TIMEOUT_SECONDS
BUFFER_SIZE = settings.BUFFER_SIZE
DEFAULT_ROTATION_INTERVAL = settings.default_rotation_interval
MAX_ROTATION_ATTEMPTS = settings.max_rotation_attempts
ROTATION_TIMEOUT_SECONDS = settings.rotation_timeout_seconds
ROTATION_RETRY_DELAY_SECONDS = settings.rotation_retry_delay_seconds
MAX_DEVICES = settings.max_devices
MAX_REQUESTS_PER_MINUTE = settings.max_requests_per_minute
HEALTH_CHECK_INTERVAL = settings.health_check_interval
HEARTBEAT_TIMEOUT = settings.heartbeat_timeout
LOG_RETENTION_DAYS = settings.log_retention_days
