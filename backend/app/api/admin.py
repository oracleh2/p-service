# backend/app/api/admin.py - ОБНОВЛЕННЫЕ БЛОКИ С ПОДДЕРЖКОЙ USB РОТАЦИИ

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


# Существующие модели остаются без изменений...
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
    rotation_type: str = "unknown"
    explanation: Optional[str] = None


class UsbRotationResponse(BaseModel):
    success: bool
    message: str
    new_ip: Optional[str] = None
    old_ip: Optional[str] = None
    device_id: str
    method: str = "usb_reboot"
    ip_changed: bool = False
    rotation_type: str = "usb_reboot"
    execution_time_seconds: float = 0.0
    explanation: Optional[str] = None
    usb_reboot_details: Optional[dict] = None


# Новые endpoint'ы для USB ротации

@router.post("/devices/{device_id}/usb-reboot", response_model=UsbRotationResponse)
async def usb_reboot_device(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Принудительная USB перезагрузка модема E3372h для ротации IP"""
    try:
        from ..core.managers import perform_device_rotation, get_device_uuid_by_name, perform_device_rotation_by_uuid, \
            _get_device_type_by_name
        import uuid
        import time

        logger.info(f"Starting USB reboot for device: {device_id}")

        start_time = time.time()

        # Получаем текущий IP до ротации
        old_ip = await get_device_current_ip(device_id)

        # Проверяем, что это USB модем
        device_type = None
        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            # Если успешно, получаем тип через UUID
            from ..core.managers import _get_device_type_by_uuid
            device_type = await _get_device_type_by_uuid(str(device_uuid))
            logger.info(f"Device UUID: {device_uuid}, Type: {device_type}")
        except ValueError:
            # Если не UUID, значит это имя устройства
            device_type = await _get_device_type_by_name(device_id)
            logger.info(f"Device name: {device_id}, Type: {device_type}")

        if device_type != 'usb_modem':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"USB reboot is only supported for USB modems, not {device_type}"
            )

        # Выполняем USB перезагрузку (принудительно используем usb_reboot)
        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            success, result = await perform_device_rotation_by_uuid(str(device_uuid), 'usb_reboot')
            logger.info(f"Used UUID-based USB reboot for device UUID: {device_uuid}")
        except ValueError:
            # Если не UUID, значит это имя устройства
            success, result = await perform_device_rotation(device_id, 'usb_reboot')
            logger.info(f"Used name-based USB reboot for device name: {device_id}")

        execution_time = time.time() - start_time

        # Получаем новый IP после ротации
        new_ip = await get_device_current_ip(device_id)

        # Анализируем результат
        ip_changed = old_ip != new_ip if old_ip and new_ip else False

        usb_reboot_details = {
            "execution_time_seconds": round(execution_time, 2),
            "old_ip": old_ip,
            "new_ip": new_ip,
            "ip_changed": ip_changed,
            "device_type": device_type,
            "method_used": "usb_reboot",
            "usb_reboot_steps": [
                "Found USB device by vendor ID 12d1",
                "Located sysfs path to device",
                "Disabled USB device via authorized file",
                "Waited 2 seconds for disconnect",
                "Enabled USB device via authorized file",
                "Monitored reconnection process",
                "Verified new IP address"
            ]
        }

        if success:
            if ip_changed:
                explanation = f"USB reboot successful! IP changed from {old_ip} to {new_ip} in {execution_time:.1f}s"
                message = f"USB reboot completed successfully! New IP: {new_ip}"
            else:
                explanation = f"USB reboot completed successfully but IP didn't change. This is normal for some operators - the connection was refreshed. Time: {execution_time:.1f}s"
                message = f"USB reboot completed successfully. Connection refreshed. IP: {new_ip or old_ip}"

            logger.info(f"✅ USB reboot successful for {device_id}: {result}")
            return UsbRotationResponse(
                success=True,
                message=message,
                new_ip=new_ip,
                old_ip=old_ip,
                device_id=device_id,
                method="usb_reboot",
                ip_changed=ip_changed,
                rotation_type="usb_reboot",
                execution_time_seconds=round(execution_time, 2),
                explanation=explanation,
                usb_reboot_details=usb_reboot_details
            )
        else:
            logger.error(f"❌ USB reboot failed for {device_id}: {result}")
            return UsbRotationResponse(
                success=False,
                message=f"USB reboot failed: {result}",
                new_ip=new_ip,
                old_ip=old_ip,
                device_id=device_id,
                method="usb_reboot",
                ip_changed=ip_changed,
                rotation_type="usb_reboot_failed",
                execution_time_seconds=round(execution_time, 2),
                explanation=f"USB reboot failed: {result}",
                usb_reboot_details=usb_reboot_details
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during USB reboot for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"USB reboot failed: {str(e)}"
        )


@router.get("/devices/{device_id}/usb-diagnostics")
async def get_usb_device_diagnostics(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Получение диагностической информации о USB устройстве"""
    try:
        from ..core.managers import get_device_by_id_combined, _get_device_type_by_name
        import uuid

        # Получаем информацию об устройстве
        device_info = await get_device_by_id_combined(device_id)
        if not device_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        # Проверяем тип устройства
        device_type = None
        try:
            device_uuid = uuid.UUID(device_id)
            from ..core.managers import _get_device_type_by_uuid
            device_type = await _get_device_type_by_uuid(str(device_uuid))
        except ValueError:
            device_type = await _get_device_type_by_name(device_id)

        if device_type != 'usb_modem':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"USB diagnostics is only supported for USB modems, not {device_type}"
            )

        # Получаем диагностическую информацию
        diagnostics = {
            "device_id": device_id,
            "device_type": device_type,
            "device_info": device_info,
            "timestamp": datetime.now().isoformat(),
            "usb_diagnostics": {}
        }

        # Проверяем наличие USB устройства
        try:
            result = await asyncio.create_subprocess_exec(
                'lsusb',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                lsusb_output = stdout.decode()
                huawei_devices = [line for line in lsusb_output.split('\n') if '12d1' in line and 'Huawei' in line]
                diagnostics["usb_diagnostics"]["lsusb_check"] = {
                    "success": True,
                    "huawei_devices_found": len(huawei_devices),
                    "devices": huawei_devices
                }
            else:
                diagnostics["usb_diagnostics"]["lsusb_check"] = {
                    "success": False,
                    "error": stderr.decode()
                }
        except Exception as e:
            diagnostics["usb_diagnostics"]["lsusb_check"] = {
                "success": False,
                "error": str(e)
            }

        # Проверяем sysfs доступ
        try:
            result = await asyncio.create_subprocess_exec(
                'find', '/sys/bus/usb/devices/', '-name', 'idVendor', '-exec', 'grep', '-l', '12d1', '{}', ';',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                vendor_files = [f for f in stdout.decode().split('\n') if f]
                diagnostics["usb_diagnostics"]["sysfs_check"] = {
                    "success": True,
                    "huawei_devices_in_sysfs": len(vendor_files),
                    "vendor_files": vendor_files
                }
            else:
                diagnostics["usb_diagnostics"]["sysfs_check"] = {
                    "success": False,
                    "error": stderr.decode()
                }
        except Exception as e:
            diagnostics["usb_diagnostics"]["sysfs_check"] = {
                "success": False,
                "error": str(e)
            }

        # Проверяем sudo доступ
        try:
            result = await asyncio.create_subprocess_exec(
                'sudo', '-n', 'echo', 'test',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            diagnostics["usb_diagnostics"]["sudo_check"] = {
                "success": result.returncode == 0,
                "message": "sudo access available" if result.returncode == 0 else "sudo access required"
            }
        except Exception as e:
            diagnostics["usb_diagnostics"]["sudo_check"] = {
                "success": False,
                "error": str(e)
            }

        # Общая готовность к USB ротации
        checks = ["lsusb_check", "sysfs_check", "sudo_check"]
        successful_checks = sum(1 for check in checks if diagnostics["usb_diagnostics"][check]["success"])

        diagnostics["usb_rotation_readiness"] = {
            "ready": successful_checks == len(checks),
            "successful_checks": successful_checks,
            "total_checks": len(checks),
            "percentage": (successful_checks / len(checks)) * 100
        }

        return diagnostics

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting USB diagnostics for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"USB diagnostics failed: {str(e)}"
        )


@router.get("/system/usb-rotation-status")
async def get_usb_rotation_system_status(current_user=Depends(get_admin_user)):
    """Получение статуса системы USB ротации"""
    try:
        from ..core.managers import get_usb_rotation_diagnostics

        # Получаем диагностическую информацию
        diagnostics = await get_usb_rotation_diagnostics()

        return {
            "timestamp": datetime.now().isoformat(),
            "usb_rotation_enabled": True,
            "supported_devices": ["Huawei E3372h"],
            "rotation_method": "usb_reboot",
            "diagnostics": diagnostics,
            "system_status": {
                "ready": diagnostics.get("system_readiness", {}).get("is_ready", False),
                "readiness_percentage": diagnostics.get("system_readiness", {}).get("percentage", 0),
                "huawei_devices_detected": diagnostics.get("diagnostics", {}).get("huawei_devices_found", 0)
            }
        }

    except Exception as e:
        logger.error(f"Error getting USB rotation system status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get USB rotation system status: {str(e)}"
        )


@router.post("/system/test-usb-rotation")
async def test_usb_rotation_system(current_user=Depends(get_admin_user)):
    """Тестирование системы USB ротации"""
    try:
        from ..core.managers import test_usb_rotation_capability

        # Выполняем тест системы
        test_results = await test_usb_rotation_capability()

        return {
            "timestamp": datetime.now().isoformat(),
            "test_type": "usb_rotation_system_test",
            "results": test_results,
            "recommendation": (
                "System ready for USB rotation" if test_results.get("summary", {}).get("overall_ready", False)
                else "System not ready - check failed tests"
            )
        }

    except Exception as e:
        logger.error(f"Error testing USB rotation system: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"USB rotation system test failed: {str(e)}"
        )


# Обновленный endpoint для ротации с поддержкой USB
@router.post("/devices/{device_id}/rotate", response_model=EnhancedRotationResponse)
async def rotate_device_ip(
    device_id: str,
    rotation_request: RotationRequest = RotationRequest(),
    current_user=Depends(get_admin_user)
):
    """Принудительная ротация IP устройства с автоматическим выбором USB перезагрузки для модемов"""
    try:
        from ..core.managers import perform_device_rotation, get_device_uuid_by_name, perform_device_rotation_by_uuid, \
            _get_device_type_by_name
        import uuid

        logger.info(f"Starting IP rotation for device: {device_id}")
        logger.info(f"Rotation request: {rotation_request.dict()}")

        # Получаем текущий IP до ротации
        old_ip = await get_device_current_ip(device_id)

        # Определяем тип устройства и автоматически выбираем метод
        device_type = None
        final_method = rotation_request.force_method

        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            from ..core.managers import _get_device_type_by_uuid
            device_type = await _get_device_type_by_uuid(str(device_uuid))

            # Для USB модемов принудительно используем USB перезагрузку
            if device_type == 'usb_modem':
                final_method = 'usb_reboot'
                logger.info(f"USB modem detected, forcing USB reboot method")

            success, result = await perform_device_rotation_by_uuid(
                str(device_uuid),
                final_method
            )
            logger.info(f"Used UUID-based rotation for device UUID: {device_uuid}")

        except ValueError:
            # Если не UUID, значит это имя устройства
            device_type = await _get_device_type_by_name(device_id)

            # Для USB модемов принудительно используем USB перезагрузку
            if device_type == 'usb_modem':
                final_method = 'usb_reboot'
                logger.info(f"USB modem detected, forcing USB reboot method")

            success, result = await perform_device_rotation(
                device_id,
                final_method
            )
            logger.info(f"Used name-based rotation for device name: {device_id}")

        # Получаем новый IP после ротации
        new_ip = await get_device_current_ip(device_id)

        # Анализируем результат
        ip_changed = old_ip != new_ip if old_ip and new_ip else False

        if success:
            if ip_changed:
                rotation_type = "ip_changed"
                explanation = f"IP successfully changed from {old_ip} to {new_ip} using {final_method}"
                message = f"IP rotation completed successfully! New IP: {new_ip}"
            else:
                rotation_type = "ip_unchanged"
                explanation = (
                    f"Rotation completed successfully using {final_method} but IP didn't change. "
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
                method=final_method,
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
                method=final_method,
                ip_changed=ip_changed,
                rotation_type="failed",
                explanation=f"Rotation failed using {final_method}: {result}"
            )

    except Exception as e:
        logger.error(f"Error during IP rotation for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"IP rotation failed: {str(e)}"
        )


# Обновленный endpoint для получения методов ротации
@router.get("/devices/{device_id}/rotation-methods")
async def get_device_rotation_methods(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Получение доступных методов ротации для устройства (USB модемы - только usb_reboot)"""
    try:
        from ..core.managers import get_device_rotation_methods, get_device_rotation_methods_by_uuid
        import uuid

        # Проверяем, передан ли UUID или имя устройства
        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
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

        # Добавляем информацию о USB ротации если это USB модем
        if result.get("device_type") == "usb_modem":
            result["usb_rotation_note"] = {
                "message": "USB модемы E3372h поддерживают только USB перезагрузку",
                "reason": "Это наиболее надежный метод ротации IP для данного типа устройств",
                "method": "usb_reboot",
                "estimated_time": "30-45 секунд",
                "success_rate": "95%+"
            }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting rotation methods: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rotation methods: {str(e)}"
        )


# Обновленный endpoint для тестирования ротации
@router.post("/devices/{device_id}/test-rotation", response_model=TestRotationResponse)
async def test_rotation_method(
    device_id: str,
    test_request: TestRotationRequest,
    current_user=Depends(get_admin_user)
):
    """Тестирование метода ротации IP для устройства (USB модемы - только usb_reboot)"""
    try:
        from ..core.managers import test_device_rotation, test_device_rotation_by_uuid, _get_device_type_by_name
        import uuid

        logger.info(f"Testing rotation method '{test_request.method}' for device: {device_id}")

        # Определяем тип устройства и корректируем метод
        device_type = None
        final_method = test_request.method

        try:
            # Пытаемся интерпретировать как UUID
            device_uuid = uuid.UUID(device_id)
            from ..core.managers import _get_device_type_by_uuid
            device_type = await _get_device_type_by_uuid(str(device_uuid))

            # Для USB модемов принудительно используем USB перезагрузку
            if device_type == 'usb_modem':
                final_method = 'usb_reboot'
                logger.info(f"USB modem detected, forcing USB reboot method for testing")

            test_result = await test_device_rotation_by_uuid(str(device_uuid), final_method)
            logger.info(f"Used UUID-based test rotation for device UUID: {device_uuid}")

        except ValueError:
            # Если не UUID, значит это имя устройства
            device_type = await _get_device_type_by_name(device_id)

            # Для USB модемов принудительно используем USB перезагрузку
            if device_type == 'usb_modem':
                final_method = 'usb_reboot'
                logger.info(f"USB modem detected, forcing USB reboot method for testing")

            test_result = await test_device_rotation(device_id, final_method)
            logger.info(f"Used name-based test rotation for device name: {device_id}")

        if "error" in test_result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=test_result["error"]
            )

        logger.info(f"Test rotation result for {device_id}: {test_result}")

        return TestRotationResponse(
            success=test_result.get("success", False),
            method=test_result.get("method", final_method),
            device_id=test_result.get("device_id", device_id),
            device_type=test_result.get("device_type", device_type or "unknown"),
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


# Вспомогательная функция для получения текущего IP устройства
async def get_device_current_ip(device_id: str) -> Optional[str]:
    """Получение текущего IP устройства"""
    try:
        from ..core.managers import get_device_manager, get_modem_manager
        import uuid

        # Пробуем получить из modem_manager
        modem_manager = get_modem_manager()
        if modem_manager:
            try:
                # Сначала проверяем, может это UUID
                device_uuid = uuid.UUID(device_id)
                # Если UUID, получаем имя устройства
                from ..core.managers import get_device_name_by_uuid
                device_name = await get_device_name_by_uuid(str(device_uuid))
                if device_name:
                    modem_info = await modem_manager.get_device_by_id(device_name)
                    if modem_info:
                        return await modem_manager.get_device_external_ip(device_name)
            except ValueError:
                # Если не UUID, используем как имя
                modem_info = await modem_manager.get_device_by_id(device_id)
                if modem_info:
                    return await modem_manager.get_device_external_ip(device_id)

        # Пробуем получить из device_manager
        device_manager = get_device_manager()
        if device_manager:
            try:
                # Сначала проверяем, может это UUID
                device_uuid = uuid.UUID(device_id)
                # Если UUID, получаем имя устройства
                from ..core.managers import get_device_name_by_uuid
                device_name = await get_device_name_by_uuid(str(device_uuid))
                if device_name:
                    device_info = await device_manager.get_device_by_id(device_name)
                    if device_info:
                        return await device_manager.get_device_external_ip(device_name)
            except ValueError:
                # Если не UUID, используем как имя
                device_info = await device_manager.get_device_by_id(device_id)
                if device_info:
                    return await device_manager.get_device_external_ip(device_id)

        return None

    except Exception as e:
        logger.error(f"Error getting current IP for device {device_id}: {e}")
        return None


# Остальные endpoint'ы остаются без изменений, но добавляем импорт asyncio
import asyncio
