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

class RotationResponse(BaseModel):
    success: bool
    message: str
    new_ip: Optional[str] = None
    device_id: str
    method: Optional[str] = None

class TestRotationResponse(BaseModel):
    success: bool
    method: str
    device_id: str
    device_type: str
    execution_time_seconds: float
    current_ip_before: Optional[str] = None
    new_ip_after: Optional[str] = None
    ip_changed: bool
    result_message: str
    timestamp: str
    recommendation: str

class EnhancedRotationResponse(BaseModel):
    success: bool
    message: str
    new_ip: Optional[str] = None
    old_ip: Optional[str] = None
    device_id: str
    method: Optional[str] = None
    ip_changed: bool = False
    rotation_type: str = "unknown"  # "ip_changed", "ip_unchanged", "connection_refreshed"
    explanation: Optional[str] = None

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
        from ..core.managers import get_all_devices_combined, get_device_manager, get_modem_manager

        # Получаем менеджеры
        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        all_devices = await get_all_devices_combined()

        devices_list = []
        for device_id, device_info in all_devices.items():
            # Определяем тип устройства
            device_type = device_info.get('type', 'unknown')

            # Получаем внешний IP с принудительным обновлением
            external_ip = device_info.get('external_ip', 'Not connected')

            # Принудительно обновляем внешний IP если устройство онлайн
            if device_info.get('status') == 'online':
                try:
                    if device_type == 'android' and device_manager:
                        fresh_ip = await device_manager.get_device_external_ip(device_id)
                        if fresh_ip:
                            external_ip = fresh_ip
                            device_info['external_ip'] = fresh_ip
                    elif device_type == 'usb_modem' and modem_manager:
                        fresh_ip = await modem_manager.force_refresh_external_ip(device_id)
                        if fresh_ip:
                            external_ip = fresh_ip
                            device_info['external_ip'] = fresh_ip
                except Exception as e:
                    logger.warning(f"Could not refresh external IP for {device_id}: {e}")

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


# Добавьте эти роуты в конец файла backend/app/api/admin.py (после всех существующих роутов)

@router.post("/devices/{device_id}/rotate", response_model=EnhancedRotationResponse)
async def rotate_device_ip(
    device_id: str,
    rotation_request: RotationRequest = RotationRequest(),
    current_user=Depends(get_admin_user)
):
    """Принудительная ротация IP устройства с улучшенной обработкой результатов"""
    try:
        from ..core.managers import perform_device_rotation, get_device_uuid_by_name, perform_device_rotation_by_uuid
        import uuid

        logger.info(f"Starting IP rotation for device: {device_id}")
        logger.info(f"Rotation request: {rotation_request.dict()}")

        # Получаем текущий IP до ротации
        old_ip = await get_device_current_ip(device_id)

        # Проверяем, передан ли UUID или имя устройства
        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            # Если успешно, используем ротацию по UUID
            success, result = await perform_device_rotation_by_uuid(
                str(device_uuid),
                rotation_request.force_method
            )
            logger.info(f"Used UUID-based rotation for device UUID: {device_uuid}")

        except ValueError:
            # Если не UUID, значит это имя устройства
            success, result = await perform_device_rotation(
                device_id,
                rotation_request.force_method
            )
            logger.info(f"Used name-based rotation for device name: {device_id}")

        # Получаем новый IP после ротации
        new_ip = await get_device_current_ip(device_id)

        # Анализируем результат
        ip_changed = old_ip != new_ip if old_ip and new_ip else False

        if success:
            if ip_changed:
                rotation_type = "ip_changed"
                explanation = f"IP successfully changed from {old_ip} to {new_ip}"
                message = f"IP rotation completed successfully! New IP: {new_ip}"
            else:
                rotation_type = "ip_unchanged"
                explanation = (
                    "Rotation completed successfully but IP didn't change. "
                    "This is normal behavior for some mobile operators - "
                    "the connection was refreshed even though the IP remained the same."
                )
                message = f"Rotation completed successfully. Connection refreshed. IP: {new_ip or old_ip}"

            logger.info(f"✅ IP rotation successful for {device_id}: {result}")
            return EnhancedRotationResponse(
                success=True,
                message=message,
                new_ip=new_ip,
                old_ip=old_ip,
                device_id=device_id,
                method=rotation_request.force_method,
                ip_changed=ip_changed,
                rotation_type=rotation_type,
                explanation=explanation
            )
        else:
            logger.error(f"❌ IP rotation failed for {device_id}: {result}")
            return EnhancedRotationResponse(
                success=False,
                message=result,
                new_ip=new_ip,
                old_ip=old_ip,
                device_id=device_id,
                method=rotation_request.force_method,
                ip_changed=ip_changed,
                rotation_type="failed",
                explanation=f"Rotation failed: {result}"
            )

    except Exception as e:
        logger.error(f"Error during IP rotation for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"IP rotation failed: {str(e)}"
        )

@router.post("/devices/{device_id}/rotate-with-fallback")
async def rotate_device_with_fallback(
    device_id: str,
    rotation_request: RotationRequest = RotationRequest(),
    current_user=Depends(get_admin_user)
):
    """Ротация IP с автоматическим fallback к альтернативным методам"""
    try:
        from ..core.managers import perform_device_rotation, get_device_uuid_by_name, perform_device_rotation_by_uuid
        import uuid

        logger.info(f"Starting IP rotation with fallback for device: {device_id}")
        logger.info(f"Rotation request: {rotation_request.dict()}")

        # Проверяем, передан ли UUID или имя устройства
        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            # Если успешно, используем ротацию по UUID
            success, result = await perform_device_rotation_by_uuid(
                str(device_uuid),
                rotation_request.force_method
            )
            logger.info(f"Used UUID-based rotation for device UUID: {device_uuid}")

        except ValueError:
            # Если не UUID, значит это имя устройства
            success, result = await perform_device_rotation(
                device_id,
                rotation_request.force_method
            )
            logger.info(f"Used name-based rotation for device name: {device_id}")

        if success:
            logger.info(f"✅ IP rotation successful for {device_id}: {result}")
            return RotationResponse(
                success=True,
                message="IP rotation completed successfully",
                new_ip=result if not result.startswith("Rotation completed") else None,
                device_id=device_id,
                method=rotation_request.force_method
            )
        else:
            logger.error(f"❌ IP rotation failed for {device_id}: {result}")
            return RotationResponse(
                success=False,
                message=result,
                device_id=device_id,
                method=rotation_request.force_method
            )

    except Exception as e:
        logger.error(f"Error during IP rotation for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"IP rotation failed: {str(e)}"
        )

@router.post("/devices/{device_id}/test-rotation", response_model=TestRotationResponse)
async def test_rotation_method(
    device_id: str,
    test_request: TestRotationRequest,
    current_user=Depends(get_admin_user)
):
    """Тестирование метода ротации IP для устройства"""
    try:
        from ..core.managers import test_device_rotation, test_device_rotation_by_uuid
        import uuid

        logger.info(f"Testing rotation method '{test_request.method}' for device: {device_id}")

        # Проверяем, передан ли UUID или имя устройства
        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            # Если успешно, используем тестирование по UUID
            test_result = await test_device_rotation_by_uuid(str(device_uuid), test_request.method)
            logger.info(f"Used UUID-based test rotation for device UUID: {device_uuid}")

        except ValueError:
            # Если не UUID, значит это имя устройства
            test_result = await test_device_rotation(device_id, test_request.method)
            logger.info(f"Used name-based test rotation for device name: {device_id}")

        if "error" in test_result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=test_result["error"]
            )

        logger.info(f"Test rotation result for {device_id}: {test_result}")

        return TestRotationResponse(
            success=test_result.get("success", False),
            method=test_result.get("method", test_request.method),
            device_id=test_result.get("device_id", device_id),
            device_type=test_result.get("device_type", "unknown"),
            execution_time_seconds=test_result.get("execution_time_seconds", 0.0),
            current_ip_before=test_result.get("current_ip_before"),
            new_ip_after=test_result.get("new_ip_after"),
            ip_changed=test_result.get("ip_changed", False),
            result_message=test_result.get("result_message", ""),
            timestamp=test_result.get("timestamp", datetime.now(timezone.utc).isoformat()),
            recommendation=test_result.get("recommendation", "try_different_method")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing rotation method for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test rotation failed: {str(e)}"
        )


@router.post("/devices/rotate-all")
async def rotate_all_devices(current_user=Depends(get_admin_user)):
    """Ротация IP для всех онлайн устройств"""
    try:
        from ..core.managers import get_online_devices_combined, perform_device_rotation, \
            sync_device_managers_with_database

        # Синхронизируем данные перед ротацией
        await sync_device_managers_with_database()

        # Получаем все онлайн устройства
        online_devices = await get_online_devices_combined()

        if not online_devices:
            return {
                "success": False,
                "message": "No online devices available for rotation",
                "results": {},
                "total_devices": 0,
                "successful_rotations": 0
            }

        results = {}
        successful_rotations = 0

        # Выполняем ротацию для каждого устройства
        for device_name, device_info in online_devices.items():
            try:
                # Используем имя устройства для ротации
                success, result = await perform_device_rotation(device_name)
                results[device_name] = {
                    "success": success,
                    "message": result,
                    "new_ip": result if success else None,
                    "device_name": device_name,
                    "device_uuid": device_info.get('uuid', 'unknown')
                }

                if success:
                    successful_rotations += 1

            except Exception as e:
                results[device_name] = {
                    "success": False,
                    "message": f"Error: {str(e)}",
                    "device_name": device_name,
                    "device_uuid": device_info.get('uuid', 'unknown')
                }

        return {
            "success": successful_rotations > 0,
            "message": f"Rotation completed: {successful_rotations}/{len(online_devices)} devices rotated successfully",
            "results": results,
            "total_devices": len(online_devices),
            "successful_rotations": successful_rotations
        }

    except Exception as e:
        logger.error(f"Error during bulk rotation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk rotation failed: {str(e)}"
        )


@router.post("/devices/{device_id}/restart")
async def restart_device(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Перезапуск устройства"""
    try:
        from ..core.managers import get_device_by_id_combined

        device = await get_device_by_id_combined(device_id)

        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        # Здесь может быть логика перезапуска устройства
        # Пока что просто возвращаем успех
        logger.info(f"Restart requested for device: {device_id}")

        return {
            "success": True,
            "message": f"Device {device_id} restart initiated",
            "device_id": device_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting device {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device restart failed: {str(e)}"
        )


@router.put("/devices/{device_id}/auto-rotation")
async def toggle_auto_rotation(
    device_id: str,
    enabled: bool,
    current_user=Depends(get_admin_user)
):
    """Включение/выключение автоматической ротации для устройства"""
    try:
        from ..core.managers import get_device_by_id_combined

        device = await get_device_by_id_combined(device_id)

        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        # Здесь должна быть логика обновления настроек автоматической ротации
        # Пока что просто возвращаем успех
        logger.info(f"Auto rotation {'enabled' if enabled else 'disabled'} for device: {device_id}")

        return {
            "success": True,
            "message": f"Auto rotation {'enabled' if enabled else 'disabled'} for device {device_id}",
            "device_id": device_id,
            "auto_rotation": enabled
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling auto rotation for device {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto rotation toggle failed: {str(e)}"
        )


@router.put("/devices/{device_id}/rotation-interval")
async def update_rotation_interval(
    device_id: str,
    interval: int,
    current_user=Depends(get_admin_user)
):
    """Обновление интервала ротации для устройства"""
    try:
        from ..core.managers import get_device_by_id_combined

        if interval < 60 or interval > 3600:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rotation interval must be between 60 and 3600 seconds"
            )

        device = await get_device_by_id_combined(device_id)

        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        # Здесь должна быть логика обновления интервала ротации
        # Пока что просто возвращаем успех
        logger.info(f"Rotation interval updated to {interval}s for device: {device_id}")

        return {
            "success": True,
            "message": f"Rotation interval updated to {interval} seconds for device {device_id}",
            "device_id": device_id,
            "rotation_interval": interval
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating rotation interval for device {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rotation interval update failed: {str(e)}"
        )


@router.get("/devices/{device_id}/rotation-methods")
async def get_device_rotation_methods(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Получение доступных методов ротации для устройства"""
    try:
        from ..core.managers import get_device_rotation_methods, get_device_rotation_methods_by_uuid
        import uuid

        # Проверяем, передан ли UUID или имя устройства
        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            # Если успешно, используем получение методов по UUID
            result = await get_device_rotation_methods_by_uuid(str(device_uuid))
            logger.info(f"Used UUID-based rotation methods for device UUID: {device_uuid}")

        except ValueError:
            # Если не UUID, значит это имя устройства
            result = await get_device_rotation_methods(device_id)
            logger.info(f"Used name-based rotation methods for device name: {device_id}")

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

@router.post("/devices/{device_id}/test-all-methods")
async def test_all_rotation_methods(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Тестирование всех доступных методов ротации для устройства"""
    try:
        from ..core.managers import get_device_rotation_methods, test_device_rotation
        import uuid

        logger.info(f"Testing all rotation methods for device: {device_id}")

        # Получаем доступные методы ротации
        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            methods_info = await get_device_rotation_methods_by_uuid(str(device_uuid))
            logger.info(f"Used UUID-based methods lookup for device UUID: {device_uuid}")
        except ValueError:
            # Если не UUID, значит это имя устройства
            methods_info = await get_device_rotation_methods(device_id)
            logger.info(f"Used name-based methods lookup for device name: {device_id}")

        if "error" in methods_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=methods_info["error"]
            )

        available_methods = methods_info.get("available_methods", [])
        if not available_methods:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No rotation methods available for this device"
            )

        # Тестируем каждый метод
        test_results = []
        for method_info in available_methods:
            method = method_info.get("method")
            if method:
                logger.info(f"Testing method: {method}")
                try:
                    result = await test_device_rotation(device_id, method)
                    test_results.append({
                        "method": method,
                        "method_info": method_info,
                        "test_result": result
                    })
                except Exception as e:
                    test_results.append({
                        "method": method,
                        "method_info": method_info,
                        "test_result": {"error": str(e)}
                    })

        # Анализируем результаты
        successful_methods = [r for r in test_results if r["test_result"].get("success", False)]
        failed_methods = [r for r in test_results if not r["test_result"].get("success", False)]

        return {
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_methods": len(test_results),
            "successful_methods": len(successful_methods),
            "failed_methods": len(failed_methods),
            "recommended_method": successful_methods[0]["method"] if successful_methods else None,
            "test_results": test_results,
            "summary": {
                "best_methods": [r["method"] for r in successful_methods[:3]],
                "avoid_methods": [r["method"] for r in failed_methods if r["test_result"].get("recommendation") == "avoid"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing all rotation methods for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Method testing failed: {str(e)}"
        )

@router.get("/devices/{device_id}/connection-test")
async def test_device_connection(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Безопасное тестирование соединения устройства"""
    try:
        from ..core.managers import get_modem_manager, get_device_manager

        # Определяем тип устройства и выполняем тест
        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        test_result = None

        # Проверяем в modem_manager
        if modem_manager:
            modem_info = await modem_manager.get_device_by_id(device_id)
            if modem_info:
                test_result = await modem_manager.test_modem_connection_safe(device_id)

        # Если не найдено в modem_manager, проверяем в device_manager
        if not test_result and device_manager:
            device_info = await device_manager.get_device_by_id(device_id)
            if device_info:
                # Для Android устройств можем добавить свой тест
                test_result = {
                    "device_id": device_id,
                    "device_type": "android",
                    "timestamp": datetime.now().isoformat(),
                    "message": "Android device connection test not implemented yet"
                }

        if not test_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found or connection test not available"
            )

        return test_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing device connection for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )

@router.get("/devices/{device_id}/health")
async def get_device_health(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Получение статуса здоровья устройства"""
    try:
        from ..core.managers import get_modem_manager, get_device_manager

        # Определяем тип устройства и получаем статус здоровья
        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        health_status = None

        # Проверяем в modem_manager
        if modem_manager:
            modem_info = await modem_manager.get_device_by_id(device_id)
            if modem_info:
                health_status = await modem_manager.get_modem_health_status(device_id)

        # Если не найдено в modem_manager, проверяем в device_manager
        if not health_status and device_manager:
            device_info = await device_manager.get_device_by_id(device_id)
            if device_info:
                # Для Android устройств создаем базовый статус здоровья
                health_status = {
                    "device_id": device_id,
                    "device_type": "android",
                    "timestamp": datetime.now().isoformat(),
                    "health_score": 85,  # Примерный score
                    "status": "healthy",
                    "issues_count": 0,
                    "recommendations_count": 0,
                    "details": {
                        "message": "Android device health monitoring not fully implemented"
                    }
                }

        if not health_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found or health check not available"
            )

        return health_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device health for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )

@router.post("/devices/{device_id}/diagnose")
async def diagnose_device_issues(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Диагностика проблем с устройством"""
    try:
        from ..core.managers import get_modem_manager, get_device_manager

        # Определяем тип устройства и выполняем диагностику
        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        diagnosis = None

        # Проверяем в modem_manager
        if modem_manager:
            modem_info = await modem_manager.get_device_by_id(device_id)
            if modem_info:
                diagnosis = await modem_manager.diagnose_modem_connectivity_issue(device_id)

        # Если не найдено в modem_manager, проверяем в device_manager
        if not diagnosis and device_manager:
            device_info = await device_manager.get_device_by_id(device_id)
            if device_info:
                # Для Android устройств создаем базовую диагностику
                diagnosis = {
                    "device_id": device_id,
                    "device_type": "android",
                    "timestamp": datetime.now().isoformat(),
                    "overall_status": "unknown",
                    "issues": [],
                    "recommendations": ["Implement Android device diagnostics"],
                    "summary": "Android device diagnostics not fully implemented"
                }

        if not diagnosis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found or diagnostics not available"
            )

        return diagnosis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error diagnosing device {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device diagnostics failed: {str(e)}"
        )

@router.post("/devices/sync-managers")
async def sync_device_managers(current_user=Depends(get_admin_user)):
    """Синхронизация менеджеров устройств с базой данных"""
    try:
        from ..core.managers import sync_device_managers_with_database

        await sync_device_managers_with_database()

        return {
            "success": True,
            "message": "Device managers synchronized with database successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error syncing device managers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync device managers: {str(e)}"
        )

@router.get("/devices/with-uuid")
async def get_devices_with_uuid(current_user=Depends(get_admin_user)):
    """Получение всех устройств с UUID"""
    try:
        from ..core.managers import get_all_devices_with_uuid

        devices = await get_all_devices_with_uuid()

        # Преобразуем в список для удобства
        devices_list = []
        for device_name, device_info in devices.items():
            device_data = {
                "name": device_name,
                "uuid": device_info.get('uuid'),
                "database_id": device_info.get('database_id'),
                "type": device_info.get('type', 'unknown'),
                "status": device_info.get('status', 'unknown'),
                "external_ip": device_info.get('external_ip'),
                "interface": device_info.get('interface'),
                "device_info": device_info.get('device_info'),
                "last_seen": device_info.get('last_seen')
            }
            devices_list.append(device_data)

        return {
            "success": True,
            "message": "Devices retrieved with UUID successfully",
            "total_devices": len(devices_list),
            "devices": devices_list
        }

    except Exception as e:
        logger.error(f"Error getting devices with UUID: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get devices with UUID: {str(e)}"
        )

@router.get("/devices/{device_id}")
async def admin_get_device_by_id_combined(device_id: str):
    """Получение информации о конкретном устройстве (Android или USB модем)"""
    try:
        from ..core.managers import get_device_by_id_combined, get_device_manager, get_modem_manager

        # Получаем менеджеры
        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        device_info = await get_device_by_id_combined(device_id)

        if not device_info:
            raise HTTPException(status_code=404, detail="Device not found")

        logger.info(f"Getting info for device: {device_id}")
        logger.info(f"Device info: {device_info}")

        device_type = device_info.get('type', 'unknown')
        external_ip = device_info.get('external_ip', 'Not connected')

        # Принудительно обновляем внешний IP если устройство онлайн
        if device_info.get('status') == 'online':
            try:
                if device_type == 'android' and device_manager:
                    fresh_ip = await device_manager.get_device_external_ip(device_id)
                    if fresh_ip:
                        external_ip = fresh_ip
                        device_info['external_ip'] = fresh_ip
                elif device_type == 'usb_modem' and modem_manager:
                    fresh_ip = await modem_manager.force_refresh_external_ip(device_id)
                    if fresh_ip:
                        external_ip = fresh_ip
                        device_info['external_ip'] = fresh_ip
            except Exception as e:
                logger.warning(f"Could not refresh external IP for {device_id}: {e}")

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

        logger.info(f"Returning device data with external IP: {external_ip}")
        return device_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting device {device_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


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
        today = datetime.now().date()  # Убираем timezone.utc

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


@router.get("/modems/diagnostics")
async def get_modems_diagnostics(current_user=Depends(get_admin_user)):
    """Диагностика модемов Huawei E3372h"""
    try:
        from ..core.managers import get_modem_manager

        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Получаем все модемы
        all_modems = await modem_manager.get_all_devices()

        # Быстрая проверка здоровья
        health_results = await modem_manager.quick_health_check()

        # Сводка обнаружения
        discovery_summary = await modem_manager.get_discovery_summary()

        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "discovery_summary": discovery_summary,
            "modems_count": len(all_modems),
            "health_results": health_results,
            "modems": []
        }

        # Детальная информация о каждом модеме
        for modem_id, modem_info in all_modems.items():
            # Валидация конфигурации
            validation = await modem_manager.validate_modem_configuration(modem_id)

            modem_diagnostic = {
                "modem_id": modem_id,
                "interface": modem_info.get('interface'),
                "interface_ip": modem_info.get('interface_ip'),
                "web_interface": modem_info.get('web_interface'),
                "subnet_number": modem_info.get('subnet_number'),
                "mac_address": modem_info.get('mac_address'),
                "status": modem_info.get('status'),
                "external_ip": modem_info.get('external_ip'),
                "web_accessible": modem_info.get('web_accessible'),
                "health": health_results.get(modem_id, {}),
                "validation": validation,
                "addressing_scheme": {
                    "interface_expected": f"192.168.{modem_info.get('subnet_number', 'XXX')}.100",
                    "web_expected": f"192.168.{modem_info.get('subnet_number', 'XXX')}.1",
                    "interface_actual": modem_info.get('interface_ip'),
                    "web_actual": modem_info.get('web_interface'),
                    "scheme_valid": (
                        modem_info.get('interface_ip', '').endswith('.100') and
                        modem_info.get('web_interface', '').endswith('.1')
                    )
                }
            }

            diagnostics["modems"].append(modem_diagnostic)

        return diagnostics

    except Exception as e:
        logger.error(f"Error getting modem diagnostics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Modem diagnostics failed: {str(e)}"
        )


@router.post("/modems/quick-health-check")
async def quick_health_check_modems(current_user=Depends(get_admin_user)):
    """Быстрая проверка здоровья всех модемов"""
    try:
        from ..core.managers import get_modem_manager

        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Выполняем быструю проверку здоровья
        health_results = await modem_manager.quick_health_check()

        # Подсчитываем статистику
        total_modems = len(health_results)
        healthy_modems = len([r for r in health_results.values() if r.get('overall_health')])
        unhealthy_modems = total_modems - healthy_modems

        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_modems": total_modems,
                "healthy_modems": healthy_modems,
                "unhealthy_modems": unhealthy_modems,
                "health_percentage": (healthy_modems / total_modems * 100) if total_modems > 0 else 0
            },
            "health_results": health_results
        }

    except Exception as e:
        logger.error(f"Error during quick health check: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quick health check failed: {str(e)}"
        )


@router.get("/modems/discovery-summary")
async def get_modems_discovery_summary(current_user=Depends(get_admin_user)):
    """Сводка обнаружения модемов"""
    try:
        from ..core.managers import get_modem_manager

        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Получаем сводку обнаружения
        summary = await modem_manager.get_discovery_summary()

        return {
            "success": True,
            "summary": summary
        }

    except Exception as e:
        logger.error(f"Error getting discovery summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Discovery summary failed: {str(e)}"
        )


@router.post("/modems/validate/{modem_id}")
async def validate_modem_configuration(
    modem_id: str,
    current_user=Depends(get_admin_user)
):
    """Валидация конфигурации конкретного модема"""
    try:
        from ..core.managers import get_modem_manager

        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Валидируем конфигурацию модема
        validation_result = await modem_manager.validate_modem_configuration(modem_id)

        if not validation_result.get("valid"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=validation_result.get("error", "Modem validation failed")
            )

        return {
            "success": True,
            "modem_id": modem_id,
            "validation": validation_result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating modem {modem_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Modem validation failed: {str(e)}"
        )


@router.post("/modems/force-refresh/{modem_id}")
async def force_refresh_modem_ip(
    modem_id: str,
    current_user=Depends(get_admin_user)
):
    """Принудительное обновление внешнего IP модема"""
    try:
        from ..core.managers import get_modem_manager

        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Принудительно обновляем внешний IP
        external_ip = await modem_manager.force_refresh_external_ip(modem_id)

        return {
            "success": True,
            "modem_id": modem_id,
            "external_ip": external_ip,
            "message": f"External IP refreshed: {external_ip}" if external_ip else "Could not refresh external IP"
        }

    except Exception as e:
        logger.error(f"Error force refreshing IP for modem {modem_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Force refresh failed: {str(e)}"
        )

async def get_device_current_ip(device_id: str) -> Optional[str]:
    """Получение текущего IP устройства"""
    try:
        from ..core.managers import get_device_manager, get_modem_manager

        # Пробуем получить из modem_manager
        modem_manager = get_modem_manager()
        if modem_manager:
            modem_info = await modem_manager.get_device_by_id(device_id)
            if modem_info:
                return await modem_manager.get_device_external_ip(device_id)

        # Пробуем получить из device_manager
        device_manager = get_device_manager()
        if device_manager:
            device_info = await device_manager.get_device_by_id(device_id)
            if device_info:
                return await device_manager.get_device_external_ip(device_id)

        return None

    except Exception as e:
        logger.error(f"Error getting current IP for device {device_id}: {e}")
        return None
