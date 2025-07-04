from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog
import time
import uvicorn
from typing import Dict, Any

from .config import settings
from .database import init_db, check_db_connection, check_redis_connection, close_redis
from .utils.security import SecurityHeaders
from .api import admin, proxy, stats, devices, auth
from .core.simple_proxy_server import SimpleProxyServer
from .core.modem_manager import ModemManager
from .core.rotation_manager import RotationManager
from .core.health_monitor import HealthMonitor
from .core.stats_collector import StatsCollector

# Настройка логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Глобальные компоненты системы
proxy_server = None
modem_manager = None
rotation_manager = None
health_monitor = None
stats_collector = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения"""
    global proxy_server, modem_manager, rotation_manager, health_monitor, stats_collector

    logger.info("Starting Mobile Proxy Service")

    try:
        # Инициализация базы данных
        await init_db()

        # Проверка подключений
        db_ok = await check_db_connection()
        redis_ok = await check_redis_connection()

        if not db_ok:
            raise Exception("Database connection failed")
        if not redis_ok:
            raise Exception("Redis connection failed")

        # Инициализация основных компонентов
        modem_manager = ModemManager()
        rotation_manager = RotationManager(modem_manager)
        health_monitor = HealthMonitor(modem_manager)
        stats_collector = StatsCollector(modem_manager)

        # Запуск менеджера модемов
        await modem_manager.start()

        # Запуск прокси-сервера
        proxy_server = SimpleProxyServer(modem_manager)
        await proxy_server.start()

        # Запуск фоновых задач
        await rotation_manager.start()
        await health_monitor.start()
        await stats_collector.start()

        logger.info("Mobile Proxy Service started successfully")

        yield

    except Exception as e:
        logger.error("Failed to start Mobile Proxy Service", error=str(e))
        raise
    finally:
        # Остановка компонентов
        logger.info("Stopping Mobile Proxy Service")

        if proxy_server:
            await proxy_server.stop()
        if rotation_manager:
            await rotation_manager.stop()
        if health_monitor:
            await health_monitor.stop()
        if stats_collector:
            await stats_collector.stop()
        if modem_manager:
            await modem_manager.stop()

        await close_redis()

        logger.info("Mobile Proxy Service stopped")


# Создание FastAPI приложения
app = FastAPI(
    title="Mobile Proxy Service",
    description="Система управления мобильными прокси с автоматической ротацией IP",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Middleware для CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware для доверенных хостов
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.DEBUG else ["localhost", "127.0.0.1"]
)


# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Логируем входящий запрос
    logger.info(
        "Request started",
        method=request.method,
        url=str(request.url),
        client_ip=request.client.host,
        user_agent=request.headers.get("user-agent"),
    )

    # Обрабатываем запрос
    response = await call_next(request)

    # Добавляем security headers
    for header, value in SecurityHeaders.get_security_headers().items():
        response.headers[header] = value

    # Логируем ответ
    process_time = time.time() - start_time
    logger.info(
        "Request completed",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        process_time=process_time,
    )

    return response


# Обработчики ошибок
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        url=str(request.url),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error": True},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        error=str(exc),
        url=str(request.url),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": True},
    )


# Главная страница
@app.get("/")
async def root():
    return {
        "message": "Mobile Proxy Service API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Проверка состояния системы"""
    try:
        # Проверяем базу данных
        db_status = await check_db_connection()
        redis_status = await check_redis_connection()

        # Проверяем компоненты системы
        proxy_status = proxy_server.is_running() if proxy_server else False
        device_manager_status = device_manager.is_running() if device_manager else False

        # Получаем статистику устройств
        device_stats = await device_manager.get_summary() if device_manager else {}

        health_data = {
            "status": "healthy" if all([db_status, redis_status, proxy_status]) else "unhealthy",
            "timestamp": time.time(),
            "components": {
                "database": "up" if db_status else "down",
                "redis": "up" if redis_status else "down",
                "proxy_server": "up" if proxy_status else "down",
                "modem_manager": "up" if device_manager_status else "down",
            },
            "modems": device_stats,
            "settings": {
                "proxy_port": settings.PROXY_PORT,
                "api_port": settings.API_PORT,
                "max_devices": settings.MAX_DEVICES,
                "default_rotation_interval": settings.DEFAULT_ROTATION_INTERVAL,
            }
        }

        status_code = 200 if health_data["status"] == "healthy" else 503
        return JSONResponse(content=health_data, status_code=status_code)

    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return JSONResponse(
            content={
                "status": "error",
                "timestamp": time.time(),
                "error": str(e)
            },
            status_code=503
        )


# Регистрация API роутеров
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Administration"])
app.include_router(devices.router, prefix="/api/v1/devices", tags=["Devices"])
app.include_router(proxy.router, prefix="/api/v1/proxy", tags=["Proxy"])
app.include_router(stats.router, prefix="/api/v1/stats", tags=["Statistics"])


# Эндпоинт для получения информации о системе
@app.get("/api/v1/system/info")
async def get_system_info():
    """Получение информации о системе"""
    return {
        "name": "Mobile Proxy Service",
        "version": "1.0.0",
        "api_version": "v1",
        "settings": {
            "max_devices": settings.MAX_DEVICES,
            "default_rotation_interval": settings.DEFAULT_ROTATION_INTERVAL,
            "max_requests_per_minute": settings.MAX_REQUESTS_PER_MINUTE,
            "proxy_port": settings.PROXY_PORT,
            "api_port": settings.API_PORT,
        },
        "features": [
            "automatic_ip_rotation",
            "device_management",
            "request_statistics",
            "health_monitoring",
            "admin_dashboard",
            "api_access"
        ]
    }


# Функция для получения менеджеров (для использования в API)
def get_modem_manager():
    return modem_manager


def get_rotation_manager():
    return rotation_manager


def get_health_monitor():
    return health_monitor


def get_stats_collector():
    return stats_collector


def get_proxy_server():
    return proxy_server


# Запуск приложения
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )