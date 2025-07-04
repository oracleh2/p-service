# backend/app/main.py
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import logging
import time
from .config import settings

# Импорты с обработкой ошибок
# try:
#     from .config import settings
# except ImportError:
#     # Fallback конфигурация если config.py не найден
#     class FallbackSettings:
#         cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
#         debug = True
#         api_host = "0.0.0.0"
#         api_port = 8000
#
#
#     settings = FallbackSettings()

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
    allow_origins=getattr(settings, 'cors_origins', ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    logger.info(
        f"{request.method} {request.url.path} "
        f"- Status: {response.status_code} "
        f"- Time: {process_time:.3f}s"
    )
    return response


# Health check endpoint
@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "mobile-proxy-service",
        "version": "1.0.0",
        "timestamp": time.time()
    }


@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "Mobile Proxy Service API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# API v1 endpoints
@app.get("/api/v1/status")
async def api_status():
    """Статус API"""
    return {
        "api_version": "v1",
        "status": "online",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "api": "/api/v1/"
        }
    }


# Базовые endpoints для тестирования
@app.get("/api/v1/devices")
async def get_devices():
    """Получение списка устройств (заглушка)"""
    return {
        "devices": [],
        "total": 0,
        "message": "Service is running, but no devices configured yet"
    }


@app.get("/api/v1/stats/overview")
async def get_stats_overview():
    """Общая статистика (заглушка)"""
    return {
        "total_devices": 0,
        "online_devices": 0,
        "offline_devices": 0,
        "total_requests": 0,
        "success_rate": 0,
        "uptime": time.time()
    }


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if getattr(settings, 'debug', False) else "Something went wrong"
        }
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Mobile Proxy Service starting up...")
    logger.info(
        f"📡 API running on http://{getattr(settings, 'api_host', '0.0.0.0')}:{getattr(settings, 'api_port', 8000)}")
    logger.info("✅ Service ready to handle requests")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Mobile Proxy Service shutting down...")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=getattr(settings, 'api_host', '0.0.0.0'),
        port=getattr(settings, 'api_port', 8000),
        reload=getattr(settings, 'debug', False)
    )
