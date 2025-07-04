from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid

from ..database import get_db, get_system_config, update_system_config
from ..models.base import ProxyDevice, RotationConfig, SystemConfig, RequestLog, IpHistory
from ..api.auth import get_admin_user
from ..main import get_modem_manager, get_rotation_manager, get_proxy_server
from ..config import DEFAULT_SYSTEM_CONFIG

router = APIRouter()


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
    total_modems: int
    online_modems: int
    offline_modems: int
    total_requests_today: int
    successful_requests_today: int
    failed_requests_today: int
    unique_ips_today: int
    avg_response_time_ms: int
    system_uptime: str
    last_rotation_time: Optional[datetime]


class ModemManagementResponse(BaseModel):
    modem_id: str
    modem_type: str
    interface: str
    status: str
    external_ip: Optional[str]
    last_rotation: Optional[datetime]
    rotation_interval: int
    auto_rotation: bool
    total_requests: int
    success_rate: float


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
            # Если изменился глобальный интервал ротации, обновляем все модемы
            if config_update.key == "rotation_interval":
                rotation_manager = get_rotation_manager()
                if rotation_manager:
                    # Здесь можно добавить логику обновления интервалов
                    pass

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


@router.post("/system/config/reset")
async def reset_system_config(
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Сброс системных настроек к значениям по умолчанию"""
    try:
        # Удаляем все текущие настройки
        await db.execute(delete(SystemConfig))

        # Создаем настройки по умолчанию
        for key, config in DEFAULT_SYSTEM_CONFIG.items():
            system_config = SystemConfig(
                key=key,
                value=config["value"],
                description=config["description"],
                config_type=config["config_type"]
            )
            db.add(system_config)

        await db.commit()

        return {"message": "System config reset to defaults successfully"}

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset system config: {str(e)}"
        )


@router.get("/system/stats", response_model=SystemStatsResponse)
async def get_system_stats(
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение общей статистики системы"""
    try:
        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Получение информации о модемах
        modems = await modem_manager.get_all_modems()
        online_modems = 0

        for modem_id in modems.keys():
            if await modem_manager.is_modem_online(modem_id):
                online_modems += 1

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
            total_modems=len(modems),
            online_modems=online_modems,
            offline_modems=len(modems) - online_modems,
            total_requests_today=total_requests_today,
            successful_requests_today=successful_requests_today,
            failed_requests_today=failed_requests_today,
            unique_ips_today=unique_ips_today,
            avg_response_time_ms=int(avg_response_time),
            system_uptime="N/A",  # Можно добавить реальный uptime
            last_rotation_time=last_rotation_time
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system stats: {str(e)}"
        )


@router.get("/modems", response_model=List[ModemManagementResponse])
async def get_modems_management(
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение списка модемов для управления"""
    try:
        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        modems = await modem_manager.get_all_modems()
        modem_responses = []

        for modem_id, modem_info in modems.items():
            # Получение информации о модеме из БД
            try:
                device_uuid = uuid.UUID(modem_id)
                stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()
            except:
                device = None

            # Получение конфигурации ротации
            rotation_config = None
            if device:
                stmt = select(RotationConfig).where(RotationConfig.device_id == device.id)
                result = await db.execute(stmt)
                rotation_config = result.scalar_one_or_none()

            # Получение статуса
            is_online = await modem_manager.is_modem_online(modem_id)
            external_ip = await modem_manager.get_modem_external_ip(modem_id)

            # Расчет success rate
            success_rate = 0.0
            if device and device.total_requests > 0:
                success_rate = (device.successful_requests / device.total_requests) * 100

            modem_responses.append(ModemManagementResponse(
                modem_id=modem_id,
                modem_type=modem_info['type'],
                interface=modem_info['interface'],
                status="online" if is_online else "offline",
                external_ip=external_ip,
                last_rotation=device.last_ip_rotation if device else None,
                rotation_interval=rotation_config.rotation_interval if rotation_config else 600,
                auto_rotation=rotation_config.auto_rotation if rotation_config else True,
                total_requests=device.total_requests if device else 0,
                success_rate=success_rate
            ))

        return modem_responses

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get modems: {str(e)}"
        )


@router.post("/modems/{modem_id}/rotate")
async def rotate_modem_ip(
        modem_id: str,
        current_user=Depends(get_admin_user)
):
    """Принудительная ротация IP модема"""
    try:
        rotation_manager = get_rotation_manager()
        if not rotation_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rotation manager not available"
            )

        success = await rotation_manager.rotate_modem_ip(modem_id)

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


@router.post("/modems/rotate-all")
async def rotate_all_modems(
        current_user=Depends(get_admin_user)
):
    """Принудительная ротация IP всех модемов"""
    try:
        rotation_manager = get_rotation_manager()
        if not rotation_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rotation manager not available"
            )

        results = await rotation_manager.rotate_all_modems()

        successful = sum(1 for success in results.values() if success)
        total = len(results)

        return {
            "message": f"Rotation completed: {successful}/{total} modems rotated successfully",
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate all modems: {str(e)}"
        )


@router.put("/modems/{modem_id}/rotation-interval")
async def update_modem_rotation_interval(
        modem_id: str,
        interval: int,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Обновление интервала ротации модема"""
    try:
        if interval < 60:  # Минимум 1 минута
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rotation interval must be at least 60 seconds"
            )

        device_uuid = uuid.UUID(modem_id)

        # Обновление в БД
        stmt = update(RotationConfig).where(
            RotationConfig.device_id == device_uuid
        ).values(
            rotation_interval=interval,
            updated_at=datetime.now(timezone.utc)
        )

        result = await db.execute(stmt)
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Modem not found"
            )

        await db.commit()

        # Обновление в rotation manager
        rotation_manager = get_rotation_manager()
        if rotation_manager:
            await rotation_manager.update_modem_rotation_interval(modem_id, interval)

        return {"message": "Rotation interval updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update rotation interval: {str(e)}"
        )


@router.put("/modems/{modem_id}/auto-rotation")
async def toggle_modem_auto_rotation(
        modem_id: str,
        enabled: bool,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Включение/выключение автоматической ротации модема"""
    try:
        rotation_manager = get_rotation_manager()
        if not rotation_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rotation manager not available"
            )

        if enabled:
            success = await rotation_manager.enable_auto_rotation(modem_id)
        else:
            success = await rotation_manager.disable_auto_rotation(modem_id)

        if success:
            action = "enabled" if enabled else "disabled"
            return {"message": f"Auto rotation {action} successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to toggle auto rotation"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle auto rotation: {str(e)}"
        )


@router.get("/logs/requests")
async def get_request_logs(
        limit: int = 100,
        offset: int = 0,
        modem_id: Optional[str] = None,
        status_code: Optional[int] = None,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение логов запросов"""
    try:
        query = select(RequestLog)

        if modem_id:
            query = query.where(RequestLog.device_id == uuid.UUID(modem_id))

        if status_code:
            query = query.where(RequestLog.status_code == status_code)

        query = query.order_by(RequestLog.created_at.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        logs = result.scalars().all()

        return {
            "logs": [
                {
                    "id": str(log.id),
                    "modem_id": str(log.device_id) if log.device_id else None,
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


@router.delete("/logs/cleanup")
async def cleanup_old_logs(
        days_to_keep: int = 30,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Очистка старых логов"""
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

        # Удаление старых логов запросов
        stmt = delete(RequestLog).where(RequestLog.created_at < cutoff_date)
        result = await db.execute(stmt)
        deleted_requests = result.rowcount

        # Удаление старой истории IP
        stmt = delete(IpHistory).where(IpHistory.last_seen < cutoff_date)
        result = await db.execute(stmt)
        deleted_ips = result.rowcount

        await db.commit()

        return {
            "message": "Cleanup completed successfully",
            "deleted_request_logs": deleted_requests,
            "deleted_ip_history": deleted_ips,
            "days_kept": days_to_keep
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup logs: {str(e)}"
        )


@router.post("/system/restart")
async def restart_system(
        current_user=Depends(get_admin_user)
):
    """Перезапуск системы (только компонентов, не контейнера)"""
    try:
        # Получение всех менеджеров
        modem_manager = get_modem_manager()
        rotation_manager = get_rotation_manager()
        proxy_server = get_proxy_server()

        restart_results = {}

        # Перезапуск modem manager
        if modem_manager:
            await modem_manager.stop()
            await modem_manager.start()
            restart_results["modem_manager"] = "restarted"

        # Перезапуск rotation manager
        if rotation_manager:
            await rotation_manager.stop()
            await rotation_manager.start()
            restart_results["rotation_manager"] = "restarted"

        # Перезапуск proxy server
        if proxy_server:
            await proxy_server.stop()
            await proxy_server.start()
            restart_results["proxy_server"] = "restarted"

        return {
            "message": "System components restarted successfully",
            "results": restart_results
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart system: {str(e)}"
        )


@router.get("/system/health")
async def get_system_health(
        current_user=Depends(get_admin_user)
):
    """Детальная проверка здоровья системы"""
    try:
        health_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }

        # Проверка modem manager
        modem_manager = get_modem_manager()
        if modem_manager:
            modems = await modem_manager.get_all_modems()
            health_data["components"]["modem_manager"] = {
                "status": "running",
                "modems_count": len(modems)
            }
        else:
            health_data["components"]["modem_manager"] = {
                "status": "not_running"
            }

        # Проверка rotation manager
        rotation_manager = get_rotation_manager()
        if rotation_manager:
            health_data["components"]["rotation_manager"] = {
                "status": "running"
            }
        else:
            health_data["components"]["rotation_manager"] = {
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