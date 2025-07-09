# Обновленные блоки в backend/app/api/admin.py
import subprocess
from typing import Optional

import netifaces
from datetime import (datetime, timezone)
import time

import structlog
from fastapi import HTTPException, Depends, APIRouter
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from .auth import get_admin_user
from ..models.base import RequestLog, ProxyDevice
from ..models.database import get_db

router = APIRouter()
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

class RotationRequest(BaseModel):
    force_method: Optional[str] = None

class TestRotationRequest(BaseModel):
    method: str

@router.post("/devices/discover")
async def discover_devices(current_user=Depends(get_admin_user)):
    """Принудительное обнаружение устройств (Android и USB модемы)"""
    try:
        from ..core.managers import get_device_manager, get_modem_manager

        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        if not device_manager and not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No device managers available"
            )

        results = {
            "android_devices": {"found": 0, "devices": []},
            "usb_modems": {"found": 0, "devices": []},
            "total_found": 0,
            "errors": []
        }

        # Обнаружение Android устройств
        if device_manager:
            try:
                await device_manager.discover_all_devices()
                android_devices = await device_manager.get_all_devices()
                results["android_devices"]["found"] = len(android_devices)
                results["android_devices"]["devices"] = list(android_devices.values())
            except Exception as e:
                results["errors"].append(f"Android discovery error: {str(e)}")

        # Обнаружение USB модемов
        if modem_manager:
            try:
                await modem_manager.discover_all_devices()
                usb_modems = await modem_manager.get_all_devices()
                results["usb_modems"]["found"] = len(usb_modems)
                results["usb_modems"]["devices"] = list(usb_modems.values())
            except Exception as e:
                results["errors"].append(f"USB modem discovery error: {str(e)}")

        results["total_found"] = results["android_devices"]["found"] + results["usb_modems"]["found"]

        return {
            "message": "Device discovery completed",
            "results": results
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Discovery failed: {str(e)}"
        )


@router.get("/devices/debug")
async def debug_devices(current_user=Depends(get_admin_user)):
    """Отладочная информация об устройствах (Android и USB модемы)"""
    try:
        from ..core.managers import get_device_manager, get_modem_manager

        debug_info = {
            "android_debug": {},
            "usb_modem_debug": {},
            "system_info": {}
        }

        # Отладка Android устройств
        device_manager = get_device_manager()
        if device_manager:
            try:
                # Проверяем ADB
                result = subprocess.run(['adb', 'devices', '-l'], capture_output=True, text=True, timeout=10)
                adb_output = result.stdout
                adb_success = result.returncode == 0

                # Проверяем USB интерфейсы
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

                android_devices = await device_manager.get_all_devices()
                debug_info["android_debug"] = {
                    "adb_success": adb_success,
                    "adb_output": adb_output,
                    "usb_interfaces": usb_interfaces,
                    "devices_count": len(android_devices),
                    "devices": list(android_devices.values())
                }

            except Exception as e:
                debug_info["android_debug"]["error"] = str(e)

        # Отладка USB модемов
        modem_manager = get_modem_manager()
        if modem_manager:
            try:
                # Проверяем Huawei интерфейсы
                huawei_interfaces = []
                for interface in netifaces.interfaces():
                    mac_addr = await modem_manager.get_interface_mac(interface)
                    if mac_addr and mac_addr.lower().startswith('0c:5b:8f'):
                        interface_ip = await modem_manager.get_interface_ip(interface)
                        subnet_number = await modem_manager.extract_subnet_number(
                            interface_ip) if interface_ip else None

                        huawei_interfaces.append({
                            'interface': interface,
                            'mac': mac_addr,
                            'ip': interface_ip,
                            'subnet_number': subnet_number,
                            'web_interface': f"192.168.{subnet_number}.1" if subnet_number else None
                        })

                usb_modems = await modem_manager.get_all_devices()
                debug_info["usb_modem_debug"] = {
                    "huawei_interfaces": huawei_interfaces,
                    "modems_count": len(usb_modems),
                    "modems": list(usb_modems.values())
                }

            except Exception as e:
                debug_info["usb_modem_debug"]["error"] = str(e)

        # Системная информация
        debug_info["system_info"] = {
            "all_interfaces": netifaces.interfaces(),
            "managers_status": {
                "device_manager": "available" if device_manager else "not available",
                "modem_manager": "available" if modem_manager else "not available"
            }
        }

        return debug_info

    except Exception as e:
        return {"error": str(e)}


@router.get("/devices")
async def admin_get_devices_combined():
    """Список всех устройств (Android и USB модемы)"""
    try:
        from ..core.managers import get_all_devices_combined

        all_devices = await get_all_devices_combined()

        devices_list = []
        for device_id, device_info in all_devices.items():
            # Определяем тип устройства
            device_type = device_info.get('type', 'unknown')

            # Получаем внешний IP
            external_ip = device_info.get('external_ip', 'Not connected')

            # Базовые данные для всех типов устройств
            device_data = {
                "modem_id": device_id,
                "id": device_id,
                "device_info": device_info.get('device_info', f"Device {device_id}"),
                "name": device_info.get('device_info', f"Device {device_id}"),
                "modem_type": device_type,
                "device_type": device_type,
                "type": device_type,
                "status": device_info.get('status', 'unknown'),
                "external_ip": external_ip,
                "operator": device_info.get('operator', 'Unknown'),
                "interface": device_info.get('interface', 'Unknown'),
                "last_rotation": time.time() * 1000,  # В миллисекундах для JS
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 100.0,
                "auto_rotation": True,
                "avg_response_time": 0
            }

            # Добавляем специфичные поля для Android
            if device_type == 'android':
                device_data.update({
                    "manufacturer": device_info.get('manufacturer', 'Unknown'),
                    "model": device_info.get('model', 'Unknown'),
                    "android_version": device_info.get('android_version', 'Unknown'),
                    "battery_level": device_info.get('battery_level', 0),
                    "adb_id": device_info.get('adb_id', ''),
                    "usb_interface": device_info.get('usb_interface', 'Unknown'),
                    "routing_capable": device_info.get('routing_capable', False)
                })

            # Добавляем специфичные поля для USB модемов
            elif device_type == 'usb_modem':
                device_data.update({
                    "manufacturer": device_info.get('manufacturer', 'Huawei'),
                    "model": device_info.get('model', 'E3372h'),
                    "mac_address": device_info.get('mac_address', 'Unknown'),
                    "web_interface": device_info.get('web_interface', 'N/A'),
                    "subnet_number": device_info.get('subnet_number', 'N/A'),
                    "interface_ip": device_info.get('interface_ip', 'N/A'),
                    "web_accessible": device_info.get('web_accessible', False),
                    "signal_strength": device_info.get('signal_strength', 'N/A'),
                    "technology": device_info.get('technology', '4G LTE'),
                    "routing_capable": device_info.get('routing_capable', True)
                })

            devices_list.append(device_data)

        return devices_list

    except Exception as e:
        logger.error(f"Error getting combined devices: {e}")
        return []


@router.get("/devices/{device_id}")
async def admin_get_device_by_id_combined(device_id: str):
    """Получение информации о конкретном устройстве (Android или USB модем)"""
    try:
        from ..core.managers import get_device_by_id_combined

        device_info = await get_device_by_id_combined(device_id)

        if not device_info:
            raise HTTPException(status_code=404, detail="Device not found")

        logger.info(f"Getting info for device: {device_id}")
        logger.info(f"Device info: {device_info}")

        device_type = device_info.get('type', 'unknown')
        external_ip = device_info.get('external_ip', 'Not connected')

        # Базовые данные устройства
        device_data = {
            "modem_id": device_id,
            "modem_type": device_type,
            "device_type": device_type,
            "status": device_info.get('status', 'unknown'),
            "external_ip": external_ip,
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

        # Добавляем специфичную информацию для Android
        if device_type == 'android':
            device_data.update({
                'manufacturer': device_info.get('manufacturer', 'Unknown'),
                'model': device_info.get('model', 'Unknown'),
                'android_version': device_info.get('android_version', 'Unknown'),
                'battery_level': device_info.get('battery_level', 0),
                'adb_id': device_info.get('adb_id', ''),
                'usb_interface': device_info.get('usb_interface', 'Unknown'),
                'routing_capable': device_info.get('routing_capable', False)
            })

        # Добавляем специфичную информацию для USB модема
        elif device_type == 'usb_modem':
            device_data.update({
                'manufacturer': device_info.get('manufacturer', 'Huawei'),
                'model': device_info.get('model', 'E3372h'),
                'mac_address': device_info.get('mac_address', 'Unknown'),
                'web_interface': device_info.get('web_interface', 'N/A'),
                'subnet_number': device_info.get('subnet_number', 'N/A'),
                'interface_ip': device_info.get('interface_ip', 'N/A'),
                'web_accessible': device_info.get('web_accessible', False),
                'signal_strength': device_info.get('signal_strength', 'N/A'),
                'technology': device_info.get('technology', '4G LTE'),
                'routing_capable': device_info.get('routing_capable', True)
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

@router.get("/devices/{device_id}/rotation-methods")
async def get_device_rotation_methods(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Получение доступных методов ротации для устройства"""
    try:
        from ..core.managers import get_device_rotation_methods

        result = await get_device_rotation_methods(device_id)

        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["error"]
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting rotation methods: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rotation methods: {str(e)}"
        )

@router.post("/devices/sync-to-db")
async def sync_devices_to_database(current_user=Depends(get_admin_user)):
    """Принудительная синхронизация всех устройств с базой данных"""
    try:
        from ..core.managers import get_device_manager, get_modem_manager

        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        if not device_manager and not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No device managers available"
            )

        results = {
            "android_synced": 0,
            "usb_modems_synced": 0,
            "total_synced": 0,
            "errors": []
        }

        # Синхронизация Android устройств
        if device_manager:
            try:
                await device_manager.discover_all_devices()
                android_synced = await device_manager.force_sync_to_db()
                results["android_synced"] = android_synced
            except Exception as e:
                results["errors"].append(f"Android sync error: {str(e)}")

        # Синхронизация USB модемов
        if modem_manager:
            try:
                await modem_manager.discover_all_devices()
                modems_synced = await modem_manager.force_sync_to_db()
                results["usb_modems_synced"] = modems_synced
            except Exception as e:
                results["errors"].append(f"USB modem sync error: {str(e)}")

        results["total_synced"] = results["android_synced"] + results["usb_modems_synced"]

        # Получаем актуальный список из БД
        db_devices = []
        if device_manager:
            android_devices = await device_manager.get_devices_from_db()
            db_devices.extend(android_devices)
        if modem_manager:
            modem_devices = await modem_manager.get_devices_from_db()
            db_devices.extend(modem_devices)

        return {
            "message": "All devices synchronized to database successfully",
            "results": results,
            "database_devices": len(db_devices),
            "devices": db_devices
        }

    except Exception as e:
        logger.error(f"Error syncing devices to database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync devices to database: {str(e)}"
        )


@router.get("/devices/from-db")
async def get_devices_from_database(current_user=Depends(get_admin_user)):
    """Получение списка всех устройств из базы данных"""
    try:
        from ..core.managers import get_device_manager, get_modem_manager

        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        if not device_manager and not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No device managers available"
            )

        all_devices = []

        # Получаем Android устройства из БД
        if device_manager:
            android_devices = await device_manager.get_devices_from_db()
            all_devices.extend(android_devices)

        # Получаем USB модемы из БД
        if modem_manager:
            modem_devices = await modem_manager.get_devices_from_db()
            all_devices.extend(modem_devices)

        return {
            "message": "All devices from database",
            "android_devices": len([d for d in all_devices if d.get('device_type') == 'android']),
            "usb_modems": len([d for d in all_devices if d.get('device_type') == 'usb_modem']),
            "total_count": len(all_devices),
            "devices": all_devices
        }

    except Exception as e:
        logger.error(f"Error getting devices from database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get devices from database: {str(e)}"
        )


@router.get("/system/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    current_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение общей статистики системы (Android и USB модемы)"""
    try:
        from ..core.managers import get_devices_summary_combined

        # Получаем сводную информацию о всех устройствах
        devices_summary = await get_devices_summary_combined()

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
            total_devices=devices_summary.get("total_devices", 0),
            online_devices=devices_summary.get("total_online", 0),
            offline_devices=devices_summary.get("total_offline", 0),
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


@router.get("/system/health")
async def get_system_health(current_user=Depends(get_admin_user)):
    """Детальная проверка здоровья системы"""
    try:
        from ..core.managers import get_device_manager, get_modem_manager, get_proxy_server

        health_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }

        # Проверка device manager (Android)
        device_manager = get_device_manager()
        if device_manager:
            android_devices = await device_manager.get_all_devices()
            health_data["components"]["android_manager"] = {
                "status": "running",
                "devices_count": len(android_devices),
                "online_devices": len([d for d in android_devices.values() if d.get('status') == 'online'])
            }
        else:
            health_data["components"]["android_manager"] = {
                "status": "not_running"
            }

        # Проверка modem manager (USB модемы)
        modem_manager = get_modem_manager()
        if modem_manager:
            usb_modems = await modem_manager.get_all_devices()
            health_data["components"]["modem_manager"] = {
                "status": "running",
                "devices_count": len(usb_modems),
                "online_devices": len([d for d in usb_modems.values() if d.get('status') == 'online'])
            }
        else:
            health_data["components"]["modem_manager"] = {
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
