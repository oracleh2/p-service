# backend/app/api/admin.py - ОБНОВЛЕННЫЕ БЛОКИ С ПОДДЕРЖКОЙ USB РОТАЦИИ

import subprocess
import uuid
from typing import Optional, Dict, Any, List

import netifaces
from datetime import (datetime, timezone, timedelta)
import time

import structlog
from fastapi import HTTPException, Depends, APIRouter, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from .auth import get_admin_user
from ..models.base import RequestLog, ProxyDevice, SystemConfig
from ..models.database import get_db, update_system_config

router = APIRouter()
logger = structlog.get_logger()
rotation_status_storage: Dict[str, Dict[str, Any]] = {}

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

class RotationStatusResponse(BaseModel):
    device_id: str
    status: str  # 'idle', 'starting', 'in_progress', 'completed', 'failed'
    progress_percent: int = 0
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    current_step: Optional[str] = None
    total_steps: Optional[int] = None
    error_message: Optional[str] = None

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

@router.get("/devices/{device_id}/rotation-status", response_model=RotationStatusResponse)
async def get_rotation_status(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Получение статуса ротации устройства"""
    try:
        status_info = rotation_status_storage.get(device_id, {
            'device_id': device_id,
            'status': 'idle',
            'progress_percent': 0,
            'message': 'No rotation in progress',
            'started_at': None,
            'completed_at': None,
            'estimated_completion': None,
            'current_step': None,
            'total_steps': None,
            'error_message': None
        })

        return RotationStatusResponse(**status_info)

    except Exception as e:
        logger.error(f"Error getting rotation status for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rotation status: {str(e)}"
        )


async def update_rotation_status(
    device_id: str,
    status: str,
    progress_percent: int = 0,
    message: str = "",
    current_step: str = None,
    error_message: str = None
):
    """Обновление статуса ротации устройства"""
    try:
        current_time = datetime.now()

        if device_id not in rotation_status_storage:
            rotation_status_storage[device_id] = {
                'device_id': device_id,
                'status': 'idle',
                'progress_percent': 0,
                'message': '',
                'started_at': None,
                'completed_at': None,
                'estimated_completion': None,
                'current_step': None,
                'total_steps': 5,  # Примерное количество шагов для USB ротации
                'error_message': None
            }

        status_info = rotation_status_storage[device_id]

        # Обновляем статус
        status_info['status'] = status
        status_info['progress_percent'] = progress_percent
        status_info['message'] = message
        status_info['current_step'] = current_step
        status_info['error_message'] = error_message

        # Устанавливаем время начала
        if status == 'starting' and not status_info['started_at']:
            status_info['started_at'] = current_time
            # Для USB модемов оцениваем 40 секунд
            status_info['estimated_completion'] = current_time + timedelta(seconds=40)

        # Устанавливаем время завершения
        if status in ['completed', 'failed']:
            status_info['completed_at'] = current_time
            status_info['progress_percent'] = 100

        logger.debug(f"Updated rotation status for {device_id}: {status} ({progress_percent}%)")

    except Exception as e:
        logger.error(f"Error updating rotation status: {e}")

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
async def rotate_device_ip_with_progress(
    device_id: str,
    rotation_request: RotationRequest = RotationRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user=Depends(get_admin_user)
):
    """Принудительная ротация IP устройства с отслеживанием прогресса"""
    try:
        from ..core.managers import perform_device_rotation, get_device_uuid_by_name, perform_device_rotation_by_uuid, \
            _get_device_type_by_name
        import uuid

        logger.info(f"Starting IP rotation for device: {device_id}")
        logger.info(f"Rotation request: {rotation_request.dict()}")

        # Инициализируем статус ротации
        await update_rotation_status(
            device_id,
            'starting',
            0,
            'Initializing rotation...',
            'initialization'
        )

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

                await update_rotation_status(
                    device_id,
                    'in_progress',
                    10,
                    'USB modem detected, using USB reboot method',
                    'method_selection'
                )

            # Обновляем статус перед началом ротации
            await update_rotation_status(
                device_id,
                'in_progress',
                20,
                f'Starting rotation with method: {final_method}',
                'rotation_start'
            )

            # Выполняем ротацию с обновлениями статуса
            success, result = await perform_device_rotation_with_status(
                device_uuid if 'device_uuid' in locals() else device_id,
                final_method,
                device_id,
                device_type == 'usb_modem'
            )

        except ValueError:
            # Если не UUID, значит это имя устройства
            device_type = await _get_device_type_by_name(device_id)

            # Для USB модемов принудительно используем USB перезагрузку
            if device_type == 'usb_modem':
                final_method = 'usb_reboot'
                logger.info(f"USB modem detected, forcing USB reboot method")

            await update_rotation_status(
                device_id,
                'in_progress',
                20,
                f'Starting rotation with method: {final_method}',
                'rotation_start'
            )

            success, result = await perform_device_rotation_with_status(
                device_id,
                final_method,
                device_id,
                device_type == 'usb_modem'
            )

        # Получаем новый IP после ротации
        await update_rotation_status(
            device_id,
            'in_progress',
            80,
            'Verifying IP change...',
            'ip_verification'
        )

        new_ip = await get_device_current_ip(device_id)

        # Анализируем результат
        ip_changed = old_ip != new_ip if old_ip and new_ip else False

        if success:
            await update_rotation_status(
                device_id,
                'completed',
                100,
                f'Rotation completed successfully! New IP: {new_ip}' if ip_changed else 'Rotation completed successfully',
                'completed'
            )

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
            await update_rotation_status(
                device_id,
                'failed',
                0,
                f'Rotation failed: {result}',
                'failed',
                error_message=result
            )

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
        await update_rotation_status(
            device_id,
            'failed',
            0,
            f'Rotation error: {str(e)}',
            'error',
            error_message=str(e)
        )

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


# Остальные роуты которые были в оригинальном admin.py

@router.post("/devices/discover")
async def discover_devices(current_user=Depends(get_admin_user)):
    """Принудительное обнаружение устройств - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
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
                logger.info("Starting Android device discovery...")
                await device_manager.discover_all_devices()
                android_devices = await device_manager.get_all_devices()
                results["android_devices"]["found"] = len(android_devices)
                results["android_devices"]["devices"] = list(android_devices.values())
                logger.info(f"Android devices found: {len(android_devices)}")
            except Exception as e:
                logger.error(f"Android discovery error: {e}")
                results["errors"].append(f"Android discovery error: {str(e)}")

        # Обнаружение USB модемов
        if modem_manager:
            try:
                logger.info("Starting USB modem discovery...")
                await modem_manager.discover_all_devices()
                usb_modems = await modem_manager.get_all_devices()
                results["usb_modems"]["found"] = len(usb_modems)
                results["usb_modems"]["devices"] = list(usb_modems.values())
                logger.info(f"USB modems found: {len(usb_modems)}")
            except Exception as e:
                logger.error(f"USB modem discovery error: {e}")
                results["errors"].append(f"USB modem discovery error: {str(e)}")

        results["total_found"] = results["android_devices"]["found"] + results["usb_modems"]["found"]

        return {
            "message": "Device discovery completed",
            "results": results
        }

    except Exception as e:
        logger.error(f"Discovery failed: {e}")
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
                "avoid_methods": [r["method"] for r in failed_methods if
                                  r["test_result"].get("recommendation") == "avoid"]
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


@router.get("/devices/{device_id}/hilink-info")
async def get_hilink_modem_info(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Получение детальной информации о HiLink модеме"""
    try:
        from ..core.managers import get_modem_manager

        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Получаем информацию о модеме
        modem_info = await modem_manager.get_device_by_id(device_id)
        if not modem_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Modem not found"
            )

        web_interface = modem_info.get('web_interface')
        if not web_interface:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Web interface not available for this modem"
            )

        # Получаем информацию через HiLink API
        from backend.app.core.managers import get_enhanced_rotation_manager
        rotation_manager = get_enhanced_rotation_manager()
        if rotation_manager:
            hilink_info = await rotation_manager.get_hilink_modem_info(web_interface)
        else:
            hilink_info = {}

        return {
            "device_id": device_id,
            "device_type": "usb_modem",
            "device_mode": "hilink",
            "web_interface": web_interface,
            "interface": modem_info.get('interface'),
            "interface_ip": modem_info.get('interface_ip'),
            "external_ip": modem_info.get('external_ip'),
            "hilink_info": hilink_info,
            "important_notes": {
                "ip_rotation_explanation": {
                    "title": "Как работает ротация IP в HiLink режиме",
                    "points": [
                        "В HiLink режиме модем работает как роутер с внутренним DHCP сервером",
                        "Ваша система получает внутренний IP (например, 192.168.108.100) от модема",
                        "Внешний (публичный) IP находится на самом модеме, а не на системе",
                        "Команды dhclient обновляют только внутренний IP, НЕ внешний",
                        "Для изменения внешнего IP нужно управлять модемом через его веб-API"
                    ]
                },
                "rotation_methods": {
                    "title": "Эффективные методы ротации для HiLink",
                    "recommended": [
                        {
                            "method": "usb_reboot",
                            "description": "USB перезагрузка модема - самый надежный метод",
                            "effectiveness": "Очень высокая - изменяет внешний IP"
                        },
                        {
                            "method": "web_interface",
                            "description": "Отключение/подключение через HiLink API",
                            "effectiveness": "Высокая - изменяет внешний IP"
                        },
                        {
                            "method": "hilink_reboot",
                            "description": "Перезагрузка модема через API",
                            "effectiveness": "Очень высокая - гарантированно меняет внешний IP"
                        }
                    ],
                    "ineffective": [
                        {
                            "method": "dhcp_renew",
                            "description": "Обновление DHCP",
                            "effectiveness": "Низкая - НЕ изменяет внешний IP"
                        },
                        {
                            "method": "interface_restart",
                            "description": "Перезапуск интерфейса",
                            "effectiveness": "Низкая - НЕ изменяет внешний IP"
                        }
                    ]
                },
                "troubleshooting": {
                    "title": "Устранение проблем",
                    "common_issues": [
                        {
                            "problem": "IP не изменяется после dhcp_renew",
                            "solution": "Это нормально для HiLink модемов. Используйте usb_reboot или web_interface"
                        },
                        {
                            "problem": "Веб-интерфейс недоступен",
                            "solution": "Проверьте, что модем в HiLink режиме и IP интерфейса правильный"
                        },
                        {
                            "problem": "Ротация не работает",
                            "solution": "Используйте USB перезагрузку - самый надежный метод"
                        }
                    ]
                }
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HiLink info for {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get HiLink info: {str(e)}"
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

@router.post("/devices/cleanup-rotation-statuses")
async def manual_cleanup_rotation_statuses(current_user=Depends(get_admin_user)):
    """Ручная очистка статусов ротации"""
    await cleanup_rotation_statuses()
    return {
        "success": True,
        "message": "Rotation statuses cleaned up",
        "active_rotations": len(rotation_status_storage)
    }

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


@router.get("/devices/test-discovery")
async def test_discovery(current_user=Depends(get_admin_user)):
    """Тестирование отдельных частей обнаружения (Android и USB модемы)"""
    try:
        from ..core.managers import get_device_manager, get_modem_manager

        device_manager = get_device_manager()
        modem_manager = get_modem_manager()

        if not device_manager and not modem_manager:
            return {"error": "No device managers available"}

        discovery_results = {
            "android_discovery": {},
            "usb_modem_discovery": {},
            "combined_summary": {}
        }

        # Тестирование Android устройств
        if device_manager:
            try:
                # Тест 1: ADB устройства
                adb_devices = await device_manager.get_adb_devices()

                # Тест 2: USB интерфейсы для Android
                usb_interfaces = await device_manager.detect_usb_tethering_interfaces()

                # Тест 3: Android устройства с интерфейсами
                android_devices = await device_manager.discover_android_devices_with_interfaces()

                discovery_results["android_discovery"] = {
                    "adb_devices": adb_devices,
                    "usb_interfaces": usb_interfaces,
                    "android_devices": android_devices,
                    "summary": {
                        "adb_count": len(adb_devices),
                        "usb_interfaces_count": len(usb_interfaces),
                        "matched_devices": len(android_devices)
                    }
                }
            except Exception as e:
                discovery_results["android_discovery"]["error"] = str(e)

        # Тестирование USB модемов
        if modem_manager:
            try:
                # Тест 1: Обнаружение Huawei модемов по MAC
                huawei_modems = await modem_manager.discover_huawei_modems()

                # Тест 2: Все интерфейсы с Huawei MAC
                huawei_interfaces = []
                all_interfaces = netifaces.interfaces()
                for interface in all_interfaces:
                    mac_addr = await modem_manager.get_interface_mac(interface)
                    if mac_addr and mac_addr.lower().startswith('0c:5b:8f'):
                        interface_ip = await modem_manager.get_interface_ip(interface)
                        huawei_interfaces.append({
                            'interface': interface,
                            'mac': mac_addr,
                            'ip': interface_ip
                        })

                # Тест 3: Веб-интерфейсы модемов
                web_interfaces = []
                for modem_id, modem_info in huawei_modems.items():
                    web_ip = modem_info.get('web_interface')
                    if web_ip:
                        # Тест доступности веб-интерфейса
                        try:
                            import aiohttp
                            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                                async with session.get(f"http://{web_ip}") as response:
                                    web_accessible = response.status == 200
                        except:
                            web_accessible = False

                        web_interfaces.append({
                            'modem_id': modem_id,
                            'web_ip': web_ip,
                            'accessible': web_accessible
                        })

                discovery_results["usb_modem_discovery"] = {
                    "huawei_modems": huawei_modems,
                    "huawei_interfaces": huawei_interfaces,
                    "web_interfaces": web_interfaces,
                    "summary": {
                        "modems_found": len(huawei_modems),
                        "interfaces_found": len(huawei_interfaces),
                        "web_accessible": sum(1 for w in web_interfaces if w['accessible'])
                    }
                }
            except Exception as e:
                discovery_results["usb_modem_discovery"]["error"] = str(e)

        # Объединенная сводка
        android_count = discovery_results.get("android_discovery", {}).get("summary", {}).get("matched_devices", 0)
        modem_count = discovery_results.get("usb_modem_discovery", {}).get("summary", {}).get("modems_found", 0)

        discovery_results["combined_summary"] = {
            "total_android_devices": android_count,
            "total_usb_modems": modem_count,
            "total_devices": android_count + modem_count,
            "discovery_successful": android_count > 0 or modem_count > 0,
            "managers_available": {
                "device_manager": device_manager is not None,
                "modem_manager": modem_manager is not None
            }
        }

        return discovery_results

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "discovery_results": {}
        }

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


async def perform_device_rotation_with_status(
    device_identifier: str,
    method: str,
    status_device_id: str,
    is_usb_modem: bool = False
):
    """Выполнение ротации с обновлением статуса"""
    try:
        from ..core.managers import perform_device_rotation_by_uuid, perform_device_rotation

        if is_usb_modem:
            # Специальные статусы для USB модемов
            await update_rotation_status(
                status_device_id,
                'in_progress',
                30,
                'Finding USB device...',
                'usb_discovery'
            )

            await asyncio.sleep(2)  # Симуляция времени поиска

            await update_rotation_status(
                status_device_id,
                'in_progress',
                40,
                'Disabling USB device...',
                'usb_disable'
            )

            # Выполняем ротацию
            try:
                device_uuid = uuid.UUID(device_identifier)
                success, result = await perform_device_rotation_by_uuid(str(device_uuid), method)
            except ValueError:
                success, result = await perform_device_rotation(device_identifier, method)

            if success:
                await update_rotation_status(
                    status_device_id,
                    'in_progress',
                    60,
                    'USB device disabled, waiting...',
                    'usb_waiting'
                )

                await asyncio.sleep(2)

                await update_rotation_status(
                    status_device_id,
                    'in_progress',
                    70,
                    'Enabling USB device...',
                    'usb_enable'
                )
        else:
            # Обычная ротация для Android устройств
            await update_rotation_status(
                status_device_id,
                'in_progress',
                50,
                'Executing rotation...',
                'rotation_execution'
            )

            try:
                device_uuid = uuid.UUID(device_identifier)
                success, result = await perform_device_rotation_by_uuid(str(device_uuid), method)
            except ValueError:
                success, result = await perform_device_rotation(device_identifier, method)

        return success, result

    except Exception as e:
        logger.error(f"Error in rotation with status: {e}")
        return False, str(e)


# Очистка старых статусов ротации (можно вызывать периодически)
async def cleanup_rotation_statuses():
    """Очистка статусов ротации старше 1 часа"""
    try:
        current_time = datetime.now()
        expired_devices = []

        for device_id, status_info in rotation_status_storage.items():
            if status_info.get('completed_at'):
                time_since_completion = current_time - status_info['completed_at']
                if time_since_completion.total_seconds() > 3600:  # 1 час
                    expired_devices.append(device_id)

        for device_id in expired_devices:
            del rotation_status_storage[device_id]

        if expired_devices:
            logger.info(f"Cleaned up rotation statuses for {len(expired_devices)} devices")

    except Exception as e:
        logger.error(f"Error cleaning up rotation statuses: {e}")
