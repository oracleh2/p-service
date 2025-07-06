# backend/app/main.py
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, Response, HTTPException
import asyncio
import logging
import time
import random
from datetime import datetime, timezone
from .models.database import init_db
from .models.config import settings
from .core.modem_manager import ModemManager  # Добавить эту строку
from .api import auth, proxy, admin, stats
from .core.managers import init_managers
from .core.managers import get_modem_manager


init_managers()

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
    """Список реальных модемов"""
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        # Обновляем список модемов
        await modem_manager.discover_modems()

        # Получаем все модемы
        all_modems = await modem_manager.get_all_modems()

        modems_list = []
        for modem_id, modem_info in all_modems.items():
            # Получаем внешний IP
            external_ip = await modem_manager.get_modem_external_ip(modem_id)

            modem_data = {
                "modem_id": modem_id,
                "modem_type": modem_info['type'],
                "status": modem_info['status'],
                "external_ip": external_ip or "Not connected",
                "operator": modem_info.get('operator', 'Unknown'),
                "interface": modem_info['interface'],
                "device_info": modem_info['device_info'],
                "last_rotation": time.time(),
                "total_requests": 0,
                "success_rate": 100.0,
                "auto_rotation": True
            }

            # Добавляем специфичные для Android поля
            if modem_info['type'] == 'android':
                modem_data.update({
                    "manufacturer": modem_info.get('manufacturer', 'Unknown'),
                    "model": modem_info.get('model', 'Unknown'),
                    "android_version": modem_info.get('android_version', 'Unknown'),
                    "battery_level": modem_info.get('battery_level', 0),
                    "adb_id": modem_info.get('adb_id', ''),
                })

            modems_list.append(modem_data)

        logger.info(f"Returning {len(modems_list)} real modems")
        return modems_list

    except Exception as e:
        logger.error(f"Error getting modems: {e}")
        return []


# Добавьте этот endpoint в файл backend/app/main.py

@app.get("/admin/modems/{modem_id}")
async def admin_get_modem_by_id(modem_id: str):
    """Получение информации о конкретном модеме"""
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        # Получаем все модемы
        all_modems = await modem_manager.get_all_modems()

        if modem_id not in all_modems:
            raise HTTPException(status_code=404, detail="Modem not found")

        modem_info = all_modems[modem_id]

        # Получаем внешний IP
        external_ip = await modem_manager.get_modem_external_ip(modem_id)

        # Получаем дополнительную информацию в зависимости от типа модема
        additional_info = {}

        if modem_info['type'] == 'android':
            # Для Android устройств получаем дополнительную информацию
            device_details = await modem_manager.get_android_device_details(modem_info['interface'])
            additional_info.update({
                'manufacturer': device_details.get('manufacturer', 'Unknown'),
                'model': device_details.get('model', 'Unknown'),
                'android_version': device_details.get('android_version', 'Unknown'),
                'battery_level': device_details.get('battery_level', 0),
                'adb_id': modem_info.get('adb_id', ''),
                'usb_tethering': device_details.get('usb_tethering', False),
                'rotation_methods': ['data_toggle', 'airplane_mode']
            })
        elif modem_info['type'] == 'usb_modem':
            # Для USB модемов получаем AT-команды информацию
            usb_details = await modem_manager.get_usb_modem_details(modem_info)
            additional_info.update({
                'signal_strength': usb_details.get('signal_strength', 'N/A'),
                'operator': usb_details.get('operator', 'Unknown'),
                'technology': usb_details.get('technology', 'Unknown'),
                'temperature': usb_details.get('temperature', 'N/A'),
                'rotation_methods': ['at_commands', 'network_reset']
            })

        # Формируем полный ответ
        modem_data = {
            "modem_id": modem_id,
            "modem_type": modem_info['type'],
            "status": modem_info['status'],
            "external_ip": external_ip or "Not connected",
            "operator": modem_info.get('operator', 'Unknown'),
            "interface": modem_info['interface'],
            "device_info": modem_info['device_info'],
            "last_rotation": time.time() - 300,  # Пример: 5 минут назад
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "success_rate": 100.0,
            "avg_response_time": 250,
            "auto_rotation": True,
            "rotation_interval": 600,  # 10 минут
            "last_seen": modem_info.get('last_seen', datetime.now().isoformat()),
            **additional_info
        }

        logger.info(f"Returning detailed info for modem {modem_id}")
        return modem_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting modem {modem_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Также добавьте endpoint для статистики модема
@app.get("/admin/modems/{modem_id}/stats")
async def admin_get_modem_stats(modem_id: str):
    """Получение статистики конкретного модема"""
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        all_modems = await modem_manager.get_all_modems()

        if modem_id not in all_modems:
            raise HTTPException(status_code=404, detail="Modem not found")

        # Базовая статистика (заглушка, позже можно получать из БД)
        stats = {
            "modem_id": modem_id,
            "requests_today": 156,
            "successful_requests_today": 142,
            "failed_requests_today": 14,
            "success_rate_today": 91.0,
            "avg_response_time_today": 245,
            "unique_ips_today": 8,
            "data_transferred_mb_today": 23.4,
            "last_24h_stats": [
                {"hour": "00:00", "requests": 12, "success_rate": 95},
                {"hour": "01:00", "requests": 8, "success_rate": 100},
                {"hour": "02:00", "requests": 3, "success_rate": 100},
                # ... можно добавить больше данных
            ],
            "ip_history": [
                {"ip": "192.168.1.100", "first_seen": "2025-07-06T08:00:00", "requests": 45},
                {"ip": "192.168.1.101", "first_seen": "2025-07-06T09:30:00", "requests": 38},
                {"ip": "192.168.1.102", "first_seen": "2025-07-06T10:15:00", "requests": 23},
            ]
        }

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stats for modem {modem_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint для обновления настроек модема
@app.put("/admin/modems/{modem_id}")
async def admin_update_modem(modem_id: str, update_data: dict):
    """Обновление настроек модема"""
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        all_modems = await modem_manager.get_all_modems()

        if modem_id not in all_modems:
            raise HTTPException(status_code=404, detail="Modem not found")

        # Здесь можно добавить логику обновления настроек
        # Например, изменение интервала ротации, включение/выключение автоматической ротации и т.д.

        logger.info(f"Updated settings for modem {modem_id}: {update_data}")

        return {
            "message": f"Modem {modem_id} updated successfully",
            "updated_fields": list(update_data.keys())
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating modem {modem_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint для удаления модема
@app.delete("/admin/modems/{modem_id}")
async def admin_delete_modem(modem_id: str):
    """Удаление модема из системы"""
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        all_modems = await modem_manager.get_all_modems()

        if modem_id not in all_modems:
            raise HTTPException(status_code=404, detail="Modem not found")

        # Здесь можно добавить логику удаления модема
        logger.info(f"Deleted modem {modem_id}")

        return {"message": f"Modem {modem_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting modem {modem_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/modems/scan")
async def scan_modems():
    """Принудительное сканирование модемов"""
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        logger.info("Manual modem scan initiated")
        await modem_manager.discover_modems()

        all_modems = await modem_manager.get_all_modems()

        return {
            "message": "Modem scan completed",
            "found_modems": len(all_modems),
            "modems": list(all_modems.keys()),
            "timestamp": time.time()
        }

    except Exception as e:
        logger.error(f"Error scanning modems: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """Реальная ротация IP конкретного модема"""
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        all_modems = await modem_manager.get_all_modems()

        if modem_id not in all_modems:
            raise HTTPException(status_code=404, detail="Modem not found")

        modem = all_modems[modem_id]

        logger.info(f"Starting IP rotation for {modem_id}")

        # Выполняем ротацию в зависимости от типа модема
        if modem['type'] == 'android':
            success = await modem_manager.rotate_android_modem(modem)
        elif modem['type'] == 'usb_modem':
            success = await modem_manager.rotate_usb_modem(modem)
        else:
            success = False

        if success:
            new_ip = await modem_manager.get_modem_external_ip(modem_id)
            return {
                "message": f"IP rotation completed for {modem_id}",
                "modem_id": modem_id,
                "status": "success",
                "new_ip": new_ip,
                "timestamp": time.time()
            }
        else:
            return {
                "message": f"IP rotation failed for {modem_id}",
                "modem_id": modem_id,
                "status": "failed",
                "timestamp": time.time()
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rotating modem {modem_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

    # Запуск ModemManager (добавить этот блок)
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        await modem_manager.start()
        logger.info("✅ ModemManager started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start ModemManager: {e}")

    logger.info(f"📡 API running on http://{getattr(settings, 'api_host', '0.0.0.0')}:{getattr(settings, 'api_port', 8000)}")
    logger.info("🌐 CORS enabled for 192.168.1.50:3000")
    logger.info("✅ Service ready to handle requests")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Mobile Proxy Service shutting down...")

    # Добавить остановку ModemManager:
    modem_manager = get_modem_manager()
    if not modem_manager:
        return []
    try:
        await modem_manager.stop()
        logger.info("✅ ModemManager stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping ModemManager: {e}")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=getattr(settings, 'api_host', '0.0.0.0'),
        port=getattr(settings, 'api_port', 8000),
        reload=getattr(settings, 'debug', False)
    )
