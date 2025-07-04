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

# CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=getattr(settings, 'cors_origins', ["*"]),
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])

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

@app.options("/{full_path:path}")
async def options_handler(request: Request):
    """Обработка OPTIONS запросов для CORS"""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

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

@app.put("/admin/modems/{modem_id}/auto-rotation")
async def toggle_auto_rotation(modem_id: str, enabled: bool):
    """Переключение автоматической ротации (заглушка)"""
    return {
        "message": f"Auto rotation {'enabled' if enabled else 'disabled'} for {modem_id}",
        "modem_id": modem_id,
        "auto_rotation": enabled
    }

@app.put("/admin/modems/{modem_id}/rotation-interval")
async def update_rotation_interval(modem_id: str, interval: int):
    """Обновление интервала ротации (заглушка)"""
    return {
        "message": f"Rotation interval updated for {modem_id}",
        "modem_id": modem_id,
        "interval": interval
    }


@app.get("/stats/realtime")
async def stats_realtime():
    """Статистика в реальном времени (заглушка)"""
    return {
        "requests_per_minute": 45,
        "modems": {
            "online": 3,
            "offline": 1,
            "total": 4
        },
        "recent_activity": {
            "avg_response_time_ms": 245,
            "success_rate": 94.2
        },
        "system": {
            "cpu_usage": 12.5,
            "memory_usage": 68.3
        },
        "timestamp": time.time()
    }


@app.get("/stats/requests")
async def stats_requests(days: int = 1):
    """Статистика запросов (заглушка)"""
    import random
    from datetime import datetime, timedelta

    # Генерируем данные за указанное количество дней
    data = []
    now = datetime.now()

    for i in range(days * 24):  # По часам
        timestamp = now - timedelta(hours=i)
        data.append({
            "timestamp": timestamp.isoformat(),
            "hour": timestamp.hour,
            "total_requests": random.randint(50, 200),
            "successful_requests": random.randint(45, 190),
            "failed_requests": random.randint(5, 15),
            "avg_response_time": random.randint(100, 500)
        })

    return {
        "data": data,
        "total_requests": sum(d["total_requests"] for d in data),
        "success_rate": 94.2,
        "avg_response_time": 245
    }


@app.get("/stats/ips")
async def stats_ips(limit: int = 10):
    """Статистика IP адресов (заглушка)"""
    ips = [
        {
            "ip_address": "192.168.1.100",
            "operator": "МТС",
            "requests_count": 1250,
            "success_rate": 94.5,
            "first_seen": time.time() - 86400,
            "last_seen": time.time() - 300,
            "location": "Москва"
        },
        {
            "ip_address": "10.0.0.50",
            "operator": "Билайн",
            "requests_count": 987,
            "success_rate": 88.2,
            "first_seen": time.time() - 72000,
            "last_seen": time.time() - 600,
            "location": "СПб"
        },
        {
            "ip_address": "172.16.0.25",
            "operator": "Мегафон",
            "requests_count": 856,
            "success_rate": 96.1,
            "first_seen": time.time() - 54000,
            "last_seen": time.time() - 150,
            "location": "Екатеринбург"
        },
        {
            "ip_address": "192.168.2.75",
            "operator": "Теле2",
            "requests_count": 723,
            "success_rate": 91.3,
            "first_seen": time.time() - 43200,
            "last_seen": time.time() - 900,
            "location": "Новосибирск"
        },
        {
            "ip_address": "10.1.1.200",
            "operator": "МТС",
            "requests_count": 654,
            "success_rate": 89.7,
            "first_seen": time.time() - 36000,
            "last_seen": time.time() - 450,
            "location": "Казань"
        }
    ]

    return ips[:limit]


@app.get("/stats/export")
async def export_stats(format: str = "csv", days: int = 7):
    """Экспорт статистики (заглушка)"""
    if format == "csv":
        csv_data = """timestamp,requests,success_rate,response_time
2024-01-01T00:00:00Z,150,94.5,245
2024-01-01T01:00:00Z,120,92.3,267
2024-01-01T02:00:00Z,98,96.1,198
"""
        return csv_data
    else:
        return {
            "message": "Export completed",
            "format": format,
            "days": days,
            "records": 168
        }


@app.get("/stats/errors")
async def stats_errors(limit: int = 50):
    """Статистика ошибок (заглушка)"""
    import random
    from datetime import datetime, timedelta

    errors = []
    now = datetime.now()

    error_types = [
        "Connection timeout",
        "IP rotation failed",
        "Modem offline",
        "Rate limit exceeded",
        "DNS resolution failed"
    ]

    for i in range(limit):
        errors.append({
            "timestamp": (now - timedelta(minutes=random.randint(1, 1440))).isoformat(),
            "error_type": random.choice(error_types),
            "modem_id": f"modem_{random.randint(1, 10)}",
            "error_message": "Sample error message",
            "severity": random.choice(["low", "medium", "high"])
        })

    return errors


@app.get("/stats/performance")
async def stats_performance():
    """Статистика производительности (заглушка)"""
    return {
        "cpu_usage": {
            "current": 15.2,
            "average_1h": 12.8,
            "average_24h": 18.5
        },
        "memory_usage": {
            "current": 68.3,
            "available": 2.1,  # GB
            "total": 4.0  # GB
        },
        "disk_usage": {
            "used": 45.2,  # GB
            "free": 54.8,  # GB
            "total": 100.0  # GB
        },
        "network": {
            "requests_per_second": 15.3,
            "bandwidth_usage": 2.4,  # Mbps
            "connections": 45
        }
    }


@app.get("/stats/logs")
async def get_logs(
    limit: int = 50,
    offset: int = 0,
    level: str = None,
    modem_id: str = None,
    status_code: str = None,
    search: str = None
):
    """Получение логов (заглушка)"""
    import random
    from datetime import datetime, timedelta

    # Генерируем моковые логи
    methods = ["GET", "POST", "PUT", "DELETE"]
    status_codes = [200, 201, 400, 404, 500, 503]
    modem_ids = ["android_ABC123", "usb_0", "rpi_001", "android_XYZ789"]

    logs = []
    now = datetime.now()

    for i in range(limit):
        log_method = random.choice(methods)
        log_status = random.choice(status_codes)
        log_modem = random.choice(modem_ids)

        # Пропускаем если фильтры не совпадают
        if modem_id and log_modem != modem_id:
            continue
        if status_code and str(log_status) != status_code:
            continue

        timestamp = now - timedelta(minutes=random.randint(1, 1440))

        # Генерируем URLs для поиска
        urls = [
            "https://httpbin.org/ip",
            "https://api.example.com/data",
            "https://jsonplaceholder.typicode.com/posts",
            "https://reqres.in/api/users",
            "https://httpbin.org/get?param=value"
        ]

        target_url = random.choice(urls)
        if search and search.lower() not in target_url.lower():
            continue

        logs.append({
            "id": f"log_{i + offset}",
            "created_at": timestamp.isoformat(),
            "method": log_method,
            "status_code": log_status,
            "target_url": target_url,
            "client_ip": f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}",
            "external_ip": f"10.0.{random.randint(1, 254)}.{random.randint(1, 254)}",
            "modem_id": log_modem,
            "response_time_ms": random.randint(100, 2000),
            "request_size": random.randint(500, 5000),
            "response_size": random.randint(1000, 50000),
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "error_message": "Connection timeout" if log_status >= 500 else None
        })

    # Сортируем по времени (новые сначала)
    logs.sort(key=lambda x: x["created_at"], reverse=True)

    return {
        "logs": logs,
        "total": 1000,  # Общее количество логов
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < 1000
    }


@app.delete("/stats/logs")
async def clear_logs():
    """Очистка логов (заглушка)"""
    return {
        "message": "Logs cleared successfully",
        "cleared_count": 1000
    }


@app.get("/stats/logs/download")
async def download_logs(
    format: str = "txt",
    days: int = 7,
    level: str = None
):
    """Скачивание логов (заглушка)"""
    from datetime import datetime

    if format == "txt":
        log_content = f"""# Mobile Proxy Service Logs
# Generated: {datetime.now().isoformat()}
# Period: Last {days} days
# Level filter: {level or 'All'}

2024-01-01T10:00:00Z [INFO] android_ABC123: IP successfully rotated to 192.168.1.100
2024-01-01T10:01:00Z [INFO] usb_0: Modem came online
2024-01-01T10:02:00Z [WARNING] rpi_001: High response time detected (450ms)
2024-01-01T10:03:00Z [ERROR] android_XYZ789: Failed to rotate IP - timeout
2024-01-01T10:04:00Z [INFO] android_ABC123: Health check passed
"""
        return log_content

    return {
        "message": "Log export completed",
        "format": format,
        "days": days,
        "size": "2.4MB"
    }

@app.get("/admin/modems/list")
async def get_modems_list():
    """Простой список модемов для фильтров (заглушка)"""
    return [
        {"id": "android_ABC123", "name": "Android Device 1"},
        {"id": "usb_0", "name": "USB Modem 1"},
        {"id": "rpi_001", "name": "Raspberry Pi 1"},
        {"id": "android_XYZ789", "name": "Android Device 2"}
    ]


# Добавьте endpoints для управления пользователями:

@app.get("/admin/users")
async def get_users(limit: int = 20, offset: int = 0, search: str = None):
    """Получение списка пользователей (заглушка)"""
    import random
    from datetime import datetime, timedelta

    # Моковые пользователи по умолчанию
    default_users = [
        {
            "id": "user_1",
            "username": "admin",
            "email": "admin@localhost",
            "role": "admin",
            "is_active": True,
            "requests_limit": 100000,
            "requests_used": 15420,
            "last_login": datetime.now() - timedelta(hours=2),
            "created_at": datetime.now() - timedelta(days=30)
        }
    ]

    # Объединяем моковых пользователей с созданными
    all_users = default_users + created_users

    # Фильтрация по поиску
    if search:
        all_users = [
            user for user in all_users
            if search.lower() in user["username"].lower() or
               search.lower() in user["email"].lower()
        ]

    # Пагинация
    total = len(all_users)
    users_page = all_users[offset:offset + limit]

    # Форматируем данные для фронтенда
    formatted_users = []
    for user in users_page:
        formatted_users.append({
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "is_active": user["is_active"],
            "requests_limit": user["requests_limit"],
            "requests_used": user["requests_used"],
            "usage_percentage": round((user["requests_used"] / user["requests_limit"]) * 100, 1) if user[
                                                                                                        "requests_limit"] > 0 else 0,
            "last_login": user["last_login"].isoformat() if user.get("last_login") else None,
            "created_at": user["created_at"].isoformat(),
            "api_key": f"api_key_{user['id']}_{'*' * 20}"
        })

    return {
        "users": formatted_users,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total
    }


@app.post("/admin/users")
async def create_user(user_data: dict):
    """Создание пользователя (заглушка)"""
    import random
    from datetime import datetime

    try:
        # Валидация обязательных полей
        if not user_data.get("username"):
            raise HTTPException(status_code=400, detail="Username is required")
        if not user_data.get("email"):
            raise HTTPException(status_code=400, detail="Email is required")
        if not user_data.get("password"):
            raise HTTPException(status_code=400, detail="Password is required")

        # Проверяем уникальность username и email
        all_users = created_users + [{"username": "admin", "email": "admin@localhost"}]

        if any(user["username"] == user_data["username"] for user in all_users):
            raise HTTPException(status_code=400, detail="Username already exists")
        if any(user["email"] == user_data["email"] for user in all_users):
            raise HTTPException(status_code=400, detail="Email already exists")

        # Создаем пользователя
        new_user = {
            "id": f"user_{random.randint(1000, 9999)}",
            "username": user_data.get("username"),
            "email": user_data.get("email"),
            "role": user_data.get("role", "user"),
            "is_active": user_data.get("is_active", True),
            "requests_limit": user_data.get("requests_limit", 1000),
            "requests_used": 0,
            "created_at": datetime.now(),
            "last_login": None
        }

        # Добавляем в список созданных пользователей
        created_users.append(new_user)

        # Возвращаем данные в том же формате что и GET
        formatted_user = {
            "id": new_user["id"],
            "username": new_user["username"],
            "email": new_user["email"],
            "role": new_user["role"],
            "is_active": new_user["is_active"],
            "requests_limit": new_user["requests_limit"],
            "requests_used": new_user["requests_used"],
            "usage_percentage": 0,
            "last_login": None,
            "created_at": new_user["created_at"].isoformat(),
            "api_key": f"api_key_{new_user['id']}_{'*' * 20}"
        }

        return {
            "success": True,
            "message": "User created successfully",
            "user": formatted_user
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/users/{user_id}")
async def update_user(user_id: str, user_data: dict):
    """Обновление пользователя (заглушка)"""
    try:
        # Находим пользователя
        user_found = False

        # Ищем среди созданных пользователей
        for user in created_users:
            if user["id"] == user_id:
                # Обновляем данные
                for key, value in user_data.items():
                    if key in user:
                        user[key] = value
                user_found = True
                break

        if not user_found:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "success": True,
            "message": "User updated successfully",
            "user_id": user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: str):
    """Удаление пользователя (заглушка)"""
    global created_users
    try:
        if user_id == "user_1":
            raise HTTPException(status_code=400, detail="Cannot delete admin user")

        # Удаляем из списка созданных пользователей
        created_users = [user for user in created_users if user["id"] != user_id]

        return {
            "success": True,
            "message": "User deleted successfully",
            "deleted_user_id": user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(user_id: str):
    """Сброс пароля пользователя (заглушка)"""
    import string
    import random

    new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

    return {
        "message": "Password reset successfully",
        "user_id": user_id,
        "new_password": new_password  # В реальности отправляли бы на email
    }


@app.post("/admin/users/{user_id}/toggle-status")
async def toggle_user_status(user_id: str):
    """Переключение статуса пользователя (заглушка)"""
    return {
        "message": "User status toggled successfully",
        "user_id": user_id,
        "new_status": "active" if random.choice([True, False]) else "inactive"
    }


@app.post("/admin/users/{user_id}/reset-api-key")
async def reset_user_api_key(user_id: str):
    """Сброс API ключа пользователя (заглушка)"""
    import string
    import random

    new_api_key = ''.join(random.choices(string.ascii_letters + string.digits, k=32))

    return {
        "message": "API key reset successfully",
        "user_id": user_id,
        "api_key": new_api_key
    }


@app.get("/admin/users/stats")
async def get_users_stats():
    """Статистика пользователей (заглушка)"""
    return {
        "total_users": 4,
        "active_users": 3,
        "inactive_users": 1,
        "admin_users": 1,
        "regular_users": 3,
        "total_requests_today": 18905,
        "avg_requests_per_user": 4726
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

    # Инициализация базы данных
    try:
        from .models.database import init_db
        await init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")

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

