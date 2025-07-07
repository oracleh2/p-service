# backend/app/main.py - ОЧИЩЕННАЯ ВЕРСИЯ БЕЗ ДУБЛИРУЮЩИХ РОУТОВ

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
import time
from datetime import datetime, timezone

from .config import settings
from .api import auth, proxy, admin, stats, devices, dedicated_proxy
from .core.managers import init_managers, cleanup_managers, get_proxy_server

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание приложения FastAPI
app = FastAPI(
    title="Mobile Proxy Service API",
    description="API for managing mobile proxy devices and IP rotation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Localhost варианты
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
        # IP адрес сервера
        "http://192.168.1.50:3000",
        "http://192.168.1.50:8000",
        "http://192.168.1.50:8080",
        "http://192.168.1.50:5173",
        # Без порта
        "http://192.168.1.50",
        "http://localhost"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Origin",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
    expose_headers=["*"],
    max_age=3600,
)

# Подключение роутеров - ТОЛЬКО ПОДКЛЮЧЕНИЕ, БЕЗ ДУБЛИРОВАНИЯ
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(auth.router, prefix="/auth", tags=["auth-legacy"])  # Для совместимости с фронтендом
app.include_router(proxy.router, prefix="/api/v1/proxy", tags=["proxy"])
app.include_router(proxy.router, prefix="/proxy", tags=["proxy-legacy"])  # Для совместимости с фронтендом
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(admin.router, prefix="/admin", tags=["admin-legacy"])  # Для совместимости с фронтендом
app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(stats.router, prefix="/stats", tags=["stats-legacy"])  # Для совместимости с фронтендом

app.include_router(dedicated_proxy.router, prefix="/admin/dedicated-proxy", tags=["dedicated-proxy"])


# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Логируем входящий запрос
    logger.info(f"🔥 {request.method} {request.url} from {request.client.host}")

    response = await call_next(request)
    process_time = time.time() - start_time

    logger.info(
        f"{request.method} {request.url.path} "
        f"- Status: {response.status_code} "
        f"- Time: {process_time:.3f}s"
    )
    return response

# Базовые endpoints
@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "Mobile Proxy Service API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "mobile-proxy-service",
        "version": "1.0.0",
        "timestamp": time.time()
    }

@app.get("/api/v1/status")
async def api_status():
    """Статус API"""
    return {
        "api_version": "v1",
        "status": "online",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "api": "/api/v1/",
            "auth": "/api/v1/auth/",
            "proxy": "/api/v1/proxy/",
            "admin": "/api/v1/admin/",
            "stats": "/api/v1/stats/",
            "devices": "/api/v1/devices/"
        }
    }

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}")
    return {
        "error": "Internal server error",
        "message": str(exc) if getattr(settings, 'debug', False) else "Something went wrong"
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Mobile Proxy Service starting up...")

    # Инициализация базы данных
    try:
        from .models.database import init_db
        await init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")

    # Инициализация менеджеров
    try:
        await init_managers()
        logger.info("✅ All managers initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize managers: {e}")

    # Запуск ProxyServer
    try:
        proxy_server = get_proxy_server()
        if proxy_server and not proxy_server.is_running():
            await proxy_server.start()
            logger.info("✅ Proxy server started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start proxy server: {e}")

    logger.info(f"📡 API running on http://{getattr(settings, 'api_host', '0.0.0.0')}:{getattr(settings, 'api_port', 8000)}")
    logger.info(f"🌐 Proxy server running on http://{getattr(settings, 'proxy_host', '0.0.0.0')}:{getattr(settings, 'proxy_port', 8080)}")
    logger.info("✅ Service ready to handle requests")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Mobile Proxy Service shutting down...")

    try:
        await cleanup_managers()
        logger.info("✅ All managers stopped successfully")
    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=getattr(settings, 'api_host', '0.0.0.0'),
        port=getattr(settings, 'api_port', 8000),
        reload=getattr(settings, 'debug', False)
    )



## разобраться с этими роутами

