# backend/app/main.py
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, Response, HTTPException
import asyncio
import logging
import time
import random
from .api import auth
from .models.database import init_db
from .models.config import settings

created_users = []

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

# CORS middleware - исправленная конфигурация
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
        # Без порта (на случай nginx)
        "http://192.168.1.50",
        "http://localhost"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
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

# Роутеры - исправлено дублирование
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(auth.router, prefix="/auth", tags=["auth-legacy"])


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


# Убираем дублирующий OPTIONS обработчик - CORS middleware уже обрабатывает OPTIONS
# @app.options("/{full_path:path}")  # Закомментировано - может конфликтовать с CORS

# Health check endpoint
@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "mobile-proxy-service",
        "version": "1.0.0",
        "timestamp": time.time(),
        "cors_enabled": True
    }


@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "Mobile Proxy Service API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "cors_origins": [
            "http://192.168.1.50:3000",
            "http://localhost:3000"
        ]
    }


# Явный endpoint для проверки CORS
@app.get("/api/v1/cors-test")
async def cors_test():
    """Тест CORS"""
    return {
        "message": "CORS is working!",
        "timestamp": time.time(),
        "server": "192.168.1.50:8000"
    }


# API v1 endpoints
@app.get("/api/v1/status")
async def api_status():
    """Статус API"""
    return {
        "api_version": "v1",
        "status": "online",
        "cors_enabled": True,
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "api": "/api/v1/",
            "auth": "/api/v1/auth/",
            "cors_test": "/api/v1/cors-test"
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


# Admin endpoints
@app.get("/admin/system/health")
async def admin_system_health():
    """Состояние системы (заглушка)"""
    return {
        "status": "healthy",
        "components": {
            "proxy_server": "running",
            "database": "up",
            "redis": "up",
            "modem_manager": "up"
        },
        "uptime": time.time(),
        "timestamp": time.time()
    }


@app.get("/admin/modems")
async def admin_get_modems():
    """Список модемов (заглушка)"""
    return [
        {
            "modem_id": "android_ABC123",
            "modem_type": "android",
            "status": "online",
            "external_ip": "192.168.1.100",
            "operator": "МТС",
            "interface": "/dev/ttyUSB0",
            "last_rotation": time.time(),
            "total_requests": 1250,
            "success_rate": 94.5,
            "auto_rotation": True
        },
        {
            "modem_id": "usb_0",
            "modem_type": "usb_modem",
            "status": "offline",
            "external_ip": "10.0.0.50",
            "operator": "Билайн",
            "interface": "/dev/ttyUSB1",
            "last_rotation": time.time() - 3600,
            "total_requests": 987,
            "success_rate": 88.2,
            "auto_rotation": False
        },
        {
            "modem_id": "rpi_001",
            "modem_type": "raspberry_pi",
            "status": "online",
            "external_ip": "172.16.0.25",
            "operator": "Мегафон",
            "interface": "ppp0",
            "last_rotation": time.time() - 1800,
            "total_requests": 856,
            "success_rate": 96.1,
            "auto_rotation": True
        }
    ]


@app.get("/stats/overview")
async def stats_overview():
    """Общая статистика (заглушка)"""
    return {
        "total_modems": 3,
        "online_modems": 2,
        "offline_modems": 1,
        "total_requests": 3093,
        "successful_requests": 2876,
        "failed_requests": 217,
        "success_rate": 93,
        "avg_response_time": 245,
        "unique_ips": 15,
        "total_data_transferred": 2.4,
        "uptime": time.time()
    }


@app.get("/api/v1/admin/devices")
async def admin_get_devices():
    """Список устройств для админа (заглушка)"""
    return {
        "devices": [],
        "total": 0,
        "online": 0,
        "offline": 0,
        "maintenance": 0
    }


# Дополнительные endpoints для совместимости
@app.get("/admin/system/config")
async def admin_get_system_config():
    """Конфигурация системы (заглушка)"""
    return {
        "auto_rotation_enabled": True,
        "default_rotation_interval": 600,
        "max_devices": 50,
        "max_requests_per_minute": 100,
        "health_check_interval": 30
    }


@app.post("/admin/modems/rotate-all")
async def rotate_all_modems():
    """Ротация IP всех модемов (заглушка)"""
    return {
        "message": "IP rotation initiated for all modems",
        "total_modems": 3,
        "initiated": 2
    }


@app.post("/admin/modems/{modem_id}/rotate")
async def rotate_modem(modem_id: str):
    """Ротация IP конкретного модема (заглушка)"""
    return {
        "message": f"IP rotation initiated for {modem_id}",
        "modem_id": modem_id,
        "status": "initiated"
    }


# ... (остальные endpoints остаются без изменений)

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

    # Инициализация базы данных
    try:
        from .models.database import init_db
        await init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")

    logger.info(
        f"📡 API running on http://{getattr(settings, 'api_host', '0.0.0.0')}:{getattr(settings, 'api_port', 8000)}")
    logger.info("🌐 CORS enabled for 192.168.1.50:3000")
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
