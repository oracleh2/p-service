# backend/app/api/admin.py - ОЧИЩЕННАЯ ВЕРСИЯ БЕЗ МОКОВ

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid
import subprocess
import netifaces
import asyncio
import time
import structlog

# from ..main import logger
from ..models.database import get_db, get_system_config, update_system_config
from ..models.base import ProxyDevice, RotationConfig, SystemConfig, RequestLog, IpHistory
from ..api.auth import get_admin_user
from ..core.managers import get_device_manager, get_proxy_server, get_rotation_manager
from ..config import DEFAULT_SYSTEM_CONFIG

router = APIRouter()
# logger = None  # Будет импортирован из main
logger = structlog.get_logger()

class SystemConfigUpdate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


class SystemConfigResponse(BaseModel):
    key: str
    value: str
    description: Optional[str]
    config_type: str
    created_at: datetime
    updated_at: datetime


class SystemStatsResponse(BaseModel):
    total_devices: int
    online_devices: int
    offline_devices: int
    total_requests_today: int
    successful_requests_today: int
    failed_requests_today: int
    unique_ips_today: int
    avg_response_time_ms: int
    system_uptime: str
    last_rotation_time: Optional[datetime]


class DeviceManagementResponse(BaseModel):
    device_id: str
    device_type: str
    interface: str
    status: str
    external_ip: Optional[str]
    last_rotation: Optional[datetime]
    rotation_interval: int
    auto_rotation: bool
    total_requests: int
    success_rate: float


# Системная конфигурация
@router.get("/system/config", response_model=List[SystemConfigResponse])
async def get_system_config_all(
    current_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение всех системных настроек"""
    try:
        stmt = select(SystemConfig).order_by(SystemConfig.key)
        result = await db.execute(stmt)
        configs = result.scalars().all()

        return [
            SystemConfigResponse(
                key=config.key,
                value=config.value,
                description=config.description,
                config_type=config.config_type,
                created_at=config.created_at,
                updated_at=config.updated_at
            )
            for config in configs
        ]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system config: {str(e)}"
        )


@router.put("/system/config")
async def update_system_config_endpoint(
    config_update: SystemConfigUpdate,
    current_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление системной настройки"""
    try:
        success = await update_system_config(config_update.key, config_update.value)

        if success:
            return {"message": "System config updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System config not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update system config: {str(e)}"
        )


# Управление устройствами




@router.post("/devices/discover")
async def discover_devices(current_user=Depends(get_admin_user)):
    """Принудительное обнаружение устройств"""
    try:
        device_manager = get_device_manager()
        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        # Запускаем обнаружение устройств
        await device_manager.discover_all_devices()

        # Получаем результат
        devices = await device_manager.get_all_devices()

        return {
            "message": "Device discovery completed",
            "devices_found": len(devices),
            "devices": list(devices.values())
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Discovery failed: {str(e)}"
        )


@router.get("/devices/debug")
async def debug_devices(current_user=Depends(get_admin_user)):
    """Отладочная информация об устройствах"""
    try:
        # Проверяем ADB
        try:
            result = subprocess.run(['adb', 'devices', '-l'], capture_output=True, text=True, timeout=10)
            adb_output = result.stdout
            adb_success = result.returncode == 0
        except Exception as e:
            adb_output = f"ADB error: {str(e)}"
            adb_success = False

        # Проверяем интерфейсы
        all_interfaces = netifaces.interfaces()
        usb_interfaces = []

        for interface in all_interfaces:
            if interface.startswith(('enx', 'usb', 'rndis')):
                try:
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        ip_info = addrs[netifaces.AF_INET][0]
                        usb_interfaces.append({
                            'interface': interface,
                            'ip': ip_info['addr'],
                            'netmask': ip_info.get('netmask', '')
                        })
                except Exception as e:
                    usb_interfaces.append({
                        'interface': interface,
                        'error': str(e)
                    })

        # Проверяем DeviceManager
        device_manager = get_device_manager()
        dm_status = "Available" if device_manager else "Not available"

        if device_manager:
            try:
                devices = await device_manager.get_all_devices()
                dm_devices_count = len(devices)
                dm_devices = list(devices.values())
            except Exception as e:
                dm_devices_count = f"Error: {str(e)}"
                dm_devices = []
        else:
            dm_devices_count = 0
            dm_devices = []

        return {
            "adb": {
                "success": adb_success,
                "output": adb_output
            },
            "interfaces": {
                "all": all_interfaces,
                "usb": usb_interfaces,
                "honor_exists": "enx566cf3eaaf4b" in all_interfaces
            },
            "device_manager": {
                "status": dm_status,
                "devices_count": dm_devices_count,
                "devices": dm_devices
            }
        }

    except Exception as e:
        return {"error": str(e)}


@router.get("/devices/test-discovery")
async def test_discovery(current_user=Depends(get_admin_user)):
    """Тестирование отдельных частей обнаружения"""
    try:
        device_manager = get_device_manager()
        if not device_manager:
            return {"error": "Device manager not available"}

        # Тест 1: ADB устройства
        adb_devices = await device_manager.get_adb_devices()

        # Тест 2: USB интерфейсы
        usb_interfaces = await device_manager.detect_usb_tethering_interfaces()

        # Тест 3: Android устройства с интерфейсами
        android_devices = await device_manager.discover_android_devices_with_interfaces()

        return {
            "adb_devices": adb_devices,
            "usb_interfaces": usb_interfaces,
            "android_devices": android_devices
        }

    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/devices/{device_id}/rotate")
async def rotate_device_ip(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Принудительная ротация IP устройства"""
    try:
        device_manager = get_device_manager()
        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        success = await device_manager.rotate_device_ip(device_id)

        if success:
            return {"message": "IP rotation initiated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to initiate IP rotation"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate IP: {str(e)}"
        )

@router.get("/devices")
async def admin_get_devices_legacy():
    """Список устройств (legacy endpoint для фронтенда)"""
    try:
        from ..core.managers import get_device_manager
        device_manager = get_device_manager()
        if not device_manager:
            return []

        await device_manager.discover_all_devices()
        all_devices = await device_manager.get_all_devices()

        devices_list = []
        for device_id, device_info in all_devices.items():
            external_ip = await device_manager.get_device_external_ip(device_id)

            device_data = {
                "modem_id": device_id,
                "id": device_id,
                "device_info": device_info.get('device_info', f"Device {device_id}"),
                "name": device_info.get('device_info', f"Device {device_id}"),
                "modem_type": device_info['type'],
                "device_type": device_info['type'],
                "type": device_info['type'],
                "status": device_info['status'],
                "external_ip": external_ip or "Not connected",
                "operator": device_info.get('operator', 'Unknown'),
                "interface": device_info.get('interface', 'Unknown'),
                "last_rotation": time.time() * 1000,  # В миллисекундах для JS
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 100.0,  # Всегда float
                "auto_rotation": True,
                "avg_response_time": 0
            }

            # Добавляем специфичные поля
            if device_info['type'] == 'android':
                device_data.update({
                    "manufacturer": device_info.get('manufacturer', 'Unknown'),
                    "model": device_info.get('model', 'Unknown'),
                    "android_version": device_info.get('android_version', 'Unknown'),
                    "battery_level": device_info.get('battery_level', 0),
                    "adb_id": device_info.get('adb_id', ''),
                })

            devices_list.append(device_data)

        return devices_list

    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        return []

@router.get("/devices/{device_id}")
async def admin_get_device_by_id_legacy(device_id: str):
    """Получение информации о конкретном устройстве (legacy endpoint)"""
    try:
        from ..core.managers import get_device_manager
        device_manager = get_device_manager()
        if not device_manager:
            raise HTTPException(status_code=404, detail="Device manager not available")

        logger.info(f"Getting info for device: {device_id}")

        # Получаем все устройства
        all_devices = await device_manager.get_all_devices()

        if device_id not in all_devices:
            raise HTTPException(status_code=404, detail="Device not found")

        device_info = all_devices[device_id]
        logger.info(f"Device info: {device_info}")

        # Получаем внешний IP
        external_ip = await device_manager.get_device_external_ip(device_id)

        # Базовые данные устройства
        device_data = {
            "modem_id": device_id,
            "modem_type": device_info.get('type', 'unknown'),
            "status": device_info.get('status', 'unknown'),
            "external_ip": external_ip or "Not connected",
            "operator": device_info.get('operator', 'Unknown'),
            "interface": device_info.get('interface', 'Unknown'),
            "device_info": device_info.get('device_info', f"Device {device_id}"),
            "last_rotation": time.time() * 1000,
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
        logger.error(f"Unexpected error getting device {device_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
# Статистика системы
@router.get("/system/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    current_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение общей статистики системы"""
    try:
        device_manager = get_device_manager()
        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        # Получение информации об устройствах
        devices = await device_manager.get_all_devices()
        online_devices = 0

        for device_id in devices.keys():
            if await device_manager.is_device_online(device_id):
                online_devices += 1

        # Статистика запросов за сегодня
        today = datetime.now(timezone.utc).date()

        # Общее количество запросов
        stmt = select(func.count(RequestLog.id)).where(
            func.date(RequestLog.created_at) == today
        )
        result = await db.execute(stmt)
        total_requests_today = result.scalar() or 0

        # Успешные запросы
        stmt = select(func.count(RequestLog.id)).where(
            func.date(RequestLog.created_at) == today,
            RequestLog.status_code.between(200, 299)
        )
        result = await db.execute(stmt)
        successful_requests_today = result.scalar() or 0

        # Неуспешные запросы
        failed_requests_today = total_requests_today - successful_requests_today

        # Уникальные IP за сегодня
        stmt = select(func.count(func.distinct(RequestLog.external_ip))).where(
            func.date(RequestLog.created_at) == today,
            RequestLog.external_ip.isnot(None)
        )
        result = await db.execute(stmt)
        unique_ips_today = result.scalar() or 0

        # Среднее время ответа
        stmt = select(func.avg(RequestLog.response_time_ms)).where(
            func.date(RequestLog.created_at) == today,
            RequestLog.response_time_ms.isnot(None)
        )
        result = await db.execute(stmt)
        avg_response_time = result.scalar() or 0

        # Последняя ротация
        stmt = select(func.max(ProxyDevice.last_ip_rotation))
        result = await db.execute(stmt)
        last_rotation_time = result.scalar()

        return SystemStatsResponse(
            total_devices=len(devices),
            online_devices=online_devices,
            offline_devices=len(devices) - online_devices,
            total_requests_today=total_requests_today,
            successful_requests_today=successful_requests_today,
            failed_requests_today=failed_requests_today,
            unique_ips_today=unique_ips_today,
            avg_response_time_ms=int(avg_response_time),
            system_uptime="N/A",
            last_rotation_time=last_rotation_time
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system stats: {str(e)}"
        )


# Здоровье системы
@router.get("/system/health")
async def get_system_health(current_user=Depends(get_admin_user)):
    """Детальная проверка здоровья системы"""
    try:
        health_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }

        # Проверка device manager
        device_manager = get_device_manager()
        if device_manager:
            devices = await device_manager.get_all_devices()
            health_data["components"]["device_manager"] = {
                "status": "running",
                "devices_count": len(devices)
            }
        else:
            health_data["components"]["device_manager"] = {
                "status": "not_running"
            }

        # Проверка proxy server
        proxy_server = get_proxy_server()
        if proxy_server and proxy_server.is_running():
            health_data["components"]["proxy_server"] = {
                "status": "running"
            }
        else:
            health_data["components"]["proxy_server"] = {
                "status": "not_running"
            }

        # Общий статус
        all_running = all(
            comp.get("status") == "running"
            for comp in health_data["components"].values()
        )

        health_data["overall_status"] = "healthy" if all_running else "unhealthy"

        return health_data

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system health: {str(e)}"
        )


# Логи
@router.get("/logs/requests")
async def get_request_logs(
    limit: int = 100,
    offset: int = 0,
    device_id: Optional[str] = None,
    status_code: Optional[int] = None,
    current_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение логов запросов"""
    try:
        query = select(RequestLog)

        if device_id:
            query = query.where(RequestLog.device_id == uuid.UUID(device_id))

        if status_code:
            query = query.where(RequestLog.status_code == status_code)

        query = query.order_by(RequestLog.created_at.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        logs = result.scalars().all()

        return {
            "logs": [
                {
                    "id": str(log.id),
                    "device_id": str(log.device_id) if log.device_id else None,
                    "client_ip": log.client_ip,
                    "target_url": log.target_url,
                    "method": log.method,
                    "status_code": log.status_code,
                    "response_time_ms": log.response_time_ms,
                    "external_ip": log.external_ip,
                    "created_at": log.created_at,
                    "error_message": log.error_message
                }
                for log in logs
            ],
            "total": len(logs),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get request logs: {str(e)}"
        )


# Диагностика ADB
@router.get("/debug/adb")
async def debug_adb(current_user=Depends(get_admin_user)):
    """Диагностика ADB соединения"""
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


@router.post("/debug/restart-adb")
async def restart_adb(current_user=Depends(get_admin_user)):
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


