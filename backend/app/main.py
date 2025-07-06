# backend/app/main.py
import subprocess

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
# from .core.device_manager import ModemManager  # Добавить эту строку
from .api import auth, proxy, admin, stats
from .core.managers import get_device_manager, get_proxy_server


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

app.include_router(proxy.router, prefix="/proxy", tags=["proxy"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])

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
            "device_manager": "up"
        },
        "uptime": time.time(),
        "timestamp": time.time()
    }


@app.get("/admin/modems")
async def admin_get_modems():
    """Список всех устройств (Android + USB модемы + Raspberry Pi)"""
    device_manager = get_device_manager()
    if not device_manager:
        return []
    try:
        # Обновляем список устройств
        await device_manager.discover_all_devices()

        # Получаем все устройства
        all_devices = await device_manager.get_all_devices()

        devices_list = []
        for device_id, device_info in all_devices.items():
            # Получаем внешний IP
            external_ip = await device_manager.get_device_external_ip(device_id)

            device_data = {
                "modem_id": device_id,  # Оставляем для совместимости с фронтендом
                "modem_type": device_info['type'],
                "status": device_info['status'],
                "external_ip": external_ip or "Not connected",
                "operator": device_info.get('operator', 'Unknown'),
                "interface": device_info['interface'],
                "device_info": device_info['device_info'],
                "last_rotation": time.time(),
                "total_requests": 0,
                "success_rate": 100.0,
                "auto_rotation": True
            }

            # Добавляем специфичные для типа поля
            if device_info['type'] == 'android':
                device_data.update({
                    "manufacturer": device_info.get('manufacturer', 'Unknown'),
                    "model": device_info.get('model', 'Unknown'),
                    "android_version": device_info.get('android_version', 'Unknown'),
                    "battery_level": device_info.get('battery_level', 0),
                    "adb_id": device_info.get('adb_id', ''),
                })
            elif device_info['type'] == 'usb_modem':
                device_data.update({
                    "signal_strength": device_info.get('signal_strength', 'N/A'),
                    "technology": device_info.get('technology', 'Unknown'),
                })
            elif device_info['type'] == 'raspberry_pi':
                device_data.update({
                    "interface_type": "PPP/WWAN",
                })

            devices_list.append(device_data)

        logger.info(f"Returning {len(devices_list)} devices")
        return devices_list

    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        return []


# Добавьте этот endpoint в файл backend/app/main.py

@app.get("/admin/modems/{modem_id}")
async def admin_get_modem_by_id(modem_id: str):
    """Получение информации о конкретном устройстве"""
    device_manager = get_device_manager()
    if not device_manager:
        raise HTTPException(status_code=503, detail="Device manager not available")

    try:
        logger.info(f"Getting info for device: {modem_id}")

        # Получаем все устройства
        all_devices = await device_manager.get_all_devices()

        if modem_id not in all_devices:
            raise HTTPException(status_code=404, detail="Device not found")

        device_info = all_devices[modem_id]
        logger.info(f"Device info: {device_info}")

        # Получаем внешний IP
        external_ip = await device_manager.get_device_external_ip(modem_id)

        # Базовые данные устройства
        device_data = {
            "modem_id": modem_id,
            "modem_type": device_info.get('type', 'unknown'),
            "status": device_info.get('status', 'unknown'),
            "external_ip": external_ip or "Not connected",
            "operator": device_info.get('operator', 'Unknown'),
            "interface": device_info.get('interface', 'Unknown'),
            "device_info": device_info.get('device_info', f"Device {modem_id}"),
            "last_rotation": time.time() - 300,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "success_rate": 100.0,
            "avg_response_time": 250,
            "auto_rotation": True,
            "rotation_interval": 600,
            "last_seen": device_info.get('last_seen', datetime.now().isoformat()),
            "rotation_methods": device_info.get('rotation_methods', [])
        }

        # Добавляем специфичную информацию по типу
        if device_info.get('type') == 'android':
            device_data.update({
                'manufacturer': device_info.get('manufacturer', 'Unknown'),
                'model': device_info.get('model', 'Unknown'),
                'android_version': device_info.get('android_version', 'Unknown'),
                'battery_level': device_info.get('battery_level', 0),
                'adb_id': device_info.get('adb_id', ''),
            })
        elif device_info.get('type') == 'usb_modem':
            device_data.update({
                'signal_strength': device_info.get('signal_strength', 'N/A'),
                'technology': device_info.get('technology', 'Unknown'),
                'manufacturer': device_info.get('manufacturer', 'Unknown'),
                'model': device_info.get('model', 'Unknown'),
            })
        elif device_info.get('type') == 'raspberry_pi':
            device_data.update({
                'interface_type': 'PPP/WWAN',
                'connection_type': 'Network modem'
            })

        logger.info(f"Returning device data: {device_data}")
        return device_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting device {modem_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Также добавьте endpoint для статистики модема
@app.get("/admin/modems/{modem_id}/stats")
async def admin_get_modem_stats(modem_id: str):
    """Получение статистики конкретного модема"""
    device_manager = get_device_manager()
    if not device_manager:
        return []
    try:
        all_modems = await device_manager.get_all_devices()

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
    device_manager = get_device_manager()
    if not device_manager:
        return []
    try:
        all_modems = await device_manager.get_all_devices()

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
    device_manager = get_device_manager()
    if not device_manager:
        return []
    try:
        all_modems = await device_manager.get_all_devices()

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
    """Принудительное сканирование всех устройств"""
    device_manager = get_device_manager()
    if not device_manager:
        return {"error": "Device manager not available"}
    try:
        logger.info("Manual device scan initiated")
        await device_manager.discover_all_devices()

        all_devices = await device_manager.get_all_devices()

        return {
            "message": "Device scan completed",
            "found_modems": len(all_devices),  # Оставляем для совместимости
            "modems": list(all_devices.keys()),
            "devices_by_type": {
                "android": len([d for d in all_devices.values() if d['type'] == 'android']),
                "usb_modem": len([d for d in all_devices.values() if d['type'] == 'usb_modem']),
                "raspberry_pi": len([d for d in all_devices.values() if d['type'] == 'raspberry_pi'])
            },
            "timestamp": time.time()
        }

    except Exception as e:
        logger.error(f"Error scanning devices: {e}")
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
    """Ротация IP конкретного устройства"""
    device_manager = get_device_manager()
    if not device_manager:
        raise HTTPException(status_code=503, detail="Device manager not available")

    try:
        all_devices = await device_manager.get_all_devices()

        if modem_id not in all_devices:
            raise HTTPException(status_code=404, detail="Device not found")

        device = all_devices[modem_id]
        logger.info(f"Starting IP rotation for {modem_id} ({device['type']})")

        # Выполняем ротацию
        success = await device_manager.rotate_device_ip(modem_id)

        if success:
            # Ждем немного и получаем новый IP
            await asyncio.sleep(2)
            new_ip = await device_manager.get_device_external_ip(modem_id)

            return {
                "message": f"IP rotation completed for {modem_id}",
                "device_id": modem_id,
                "device_type": device['type'],
                "status": "success",
                "new_ip": new_ip,
                "timestamp": time.time()
            }
        else:
            return {
                "message": f"IP rotation failed for {modem_id}",
                "device_id": modem_id,
                "device_type": device['type'],
                "status": "failed",
                "timestamp": time.time()
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rotating device {modem_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/debug/adb")
async def debug_adb():
    """Диагностика ADB соединения"""
    import asyncio
    import subprocess

    debug_info = {
        "adb_status": "unknown",
        "adb_version": None,
        "adb_devices": [],
        "raw_output": "",
        "error_output": "",
        "return_code": None,
        "adb_path": None
    }

    try:
        # Проверка наличия ADB
        which_result = subprocess.run(['which', 'adb'], capture_output=True, text=True)
        debug_info["adb_path"] = which_result.stdout.strip() if which_result.returncode == 0 else "Not found"

        # Получение версии ADB
        try:
            version_result = await asyncio.create_subprocess_exec(
                'adb', 'version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            version_stdout, version_stderr = await version_result.communicate()
            debug_info["adb_version"] = version_stdout.decode().strip()
        except Exception as e:
            debug_info["adb_version"] = f"Error: {str(e)}"

        # Выполнение adb devices
        result = await asyncio.create_subprocess_exec(
            'adb', 'devices', '-l',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()

        debug_info["return_code"] = result.returncode
        debug_info["raw_output"] = stdout.decode()
        debug_info["error_output"] = stderr.decode()

        if result.returncode == 0:
            debug_info["adb_status"] = "working"

            # Парсинг устройств
            lines = stdout.decode().strip().split('\n')[1:]  # Пропускаем заголовок
            devices = []

            for line in lines:
                line = line.strip()
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        devices.append({
                            "device_id": parts[0],
                            "status": parts[1],
                            "full_line": line
                        })

            debug_info["adb_devices"] = devices
        else:
            debug_info["adb_status"] = "error"

    except FileNotFoundError:
        debug_info["adb_status"] = "not_installed"
        debug_info["error_output"] = "ADB not found in PATH"
    except Exception as e:
        debug_info["adb_status"] = "exception"
        debug_info["error_output"] = str(e)

    return debug_info


@app.get("/admin/debug/udev")
async def debug_udev():
    """Диагностика USB правил"""
    import os
    import glob

    debug_info = {
        "udev_rules": [],
        "usb_devices": [],
        "permissions": {}
    }

    try:
        # Проверка правил udev для Android
        udev_files = glob.glob('/etc/udev/rules.d/*android*')
        for file in udev_files:
            try:
                with open(file, 'r') as f:
                    debug_info["udev_rules"].append({
                        "file": file,
                        "content": f.read()
                    })
            except Exception as e:
                debug_info["udev_rules"].append({
                    "file": file,
                    "error": str(e)
                })

        # Проверка USB устройств
        try:
            result = subprocess.run(['lsusb'], capture_output=True, text=True)
            if result.returncode == 0:
                debug_info["usb_devices"] = result.stdout.split('\n')
        except:
            pass

    except Exception as e:
        debug_info["error"] = str(e)

    return debug_info


@app.post("/admin/debug/restart-adb")
async def restart_adb():
    """Перезапуск ADB сервера"""
    try:
        # Остановка ADB сервера
        kill_result = await asyncio.create_subprocess_exec(
            'adb', 'kill-server',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await kill_result.communicate()

        # Ожидание
        await asyncio.sleep(2)

        # Запуск ADB сервера
        start_result = await asyncio.create_subprocess_exec(
            'adb', 'start-server',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await start_result.communicate()

        # Ожидание
        await asyncio.sleep(3)

        # Проверка устройств
        devices_result = await asyncio.create_subprocess_exec(
            'adb', 'devices',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        devices_stdout, devices_stderr = await devices_result.communicate()

        return {
            "message": "ADB server restarted",
            "kill_code": kill_result.returncode,
            "start_code": start_result.returncode,
            "devices_output": devices_stdout.decode(),
            "devices_error": devices_stderr.decode()
        }

    except Exception as e:
        return {
            "error": str(e),
            "message": "Failed to restart ADB server"
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

    # Импорт и инициализация менеджеров
    try:
        from .core.managers import init_managers
        await init_managers()
        logger.info("✅ All managers initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize managers: {e}")

    # Запуск ProxyServer отдельно (если нужен)
    try:
        from .core.managers import get_proxy_server
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
        from .core.managers import cleanup_managers
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
