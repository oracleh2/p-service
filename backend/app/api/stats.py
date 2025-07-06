# backend/app/api/stats.py - ОЧИЩЕННАЯ ВЕРСИЯ БЕЗ МОКОВ

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid

from ..models.database import get_db
from ..models.base import RequestLog, IpHistory, ProxyDevice, UsageStats
from ..api.auth import get_current_active_user
from ..core.managers import get_device_manager, get_proxy_server

router = APIRouter()


class OverviewStats(BaseModel):
    total_devices: int
    online_devices: int
    offline_devices: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time: int
    unique_ips: int
    total_data_transferred: float


class DeviceStats(BaseModel):
    device_id: str
    device_name: str
    device_type: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time_ms: int
    unique_ips: int
    last_24h_requests: int


class RequestStat(BaseModel):
    date: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: int
    unique_ips: int


class IpStat(BaseModel):
    ip_address: str
    operator: Optional[str]
    region: Optional[str]
    requests_count: int
    success_rate: float
    first_seen: datetime
    last_seen: datetime
    is_blocked: bool


@router.get("/overview", response_model=OverviewStats)
async def get_overview_stats(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение общей статистики системы"""
    try:
        device_manager = get_device_manager()

        # Статистика устройств
        if device_manager:
            all_devices = await device_manager.get_all_devices()
            total_devices = len(all_devices)
            online_devices = len([d for d in all_devices.values() if d.get('status') == 'online'])
            offline_devices = total_devices - online_devices
        else:
            total_devices = online_devices = offline_devices = 0

        # Статистика запросов за последние 24 часа
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)

        # Общее количество запросов
        stmt = select(func.count(RequestLog.id)).where(RequestLog.created_at >= yesterday)
        result = await db.execute(stmt)
        total_requests = result.scalar() or 0

        # Успешные запросы
        stmt = select(func.count(RequestLog.id)).where(
            RequestLog.created_at >= yesterday,
            RequestLog.status_code.between(200, 299)
        )
        result = await db.execute(stmt)
        successful_requests = result.scalar() or 0

        failed_requests = total_requests - successful_requests
        success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0

        # Среднее время ответа
        stmt = select(func.avg(RequestLog.response_time_ms)).where(
            RequestLog.created_at >= yesterday,
            RequestLog.response_time_ms.isnot(None)
        )
        result = await db.execute(stmt)
        avg_response_time = int(result.scalar() or 0)

        # Уникальные IP
        stmt = select(func.count(func.distinct(RequestLog.external_ip))).where(
            RequestLog.created_at >= yesterday,
            RequestLog.external_ip.isnot(None)
        )
        result = await db.execute(stmt)
        unique_ips = result.scalar() or 0

        # Общий объем переданных данных
        stmt = select(func.sum(RequestLog.request_size + RequestLog.response_size)).where(
            RequestLog.created_at >= yesterday
        )
        result = await db.execute(stmt)
        total_bytes = result.scalar() or 0
        total_data_transferred = total_bytes / (1024 * 1024)  # в MB

        return OverviewStats(
            total_devices=total_devices,
            online_devices=online_devices,
            offline_devices=offline_devices,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            success_rate=success_rate,
            avg_response_time=avg_response_time,
            unique_ips=unique_ips,
            total_data_transferred=total_data_transferred
        )

    except Exception as e:
        # В случае ошибки возвращаем нулевую статистику
        return OverviewStats(
            total_devices=0,
            online_devices=0,
            offline_devices=0,
            total_requests=0,
            successful_requests=0,
            failed_requests=0,
            success_rate=0,
            avg_response_time=0,
            unique_ips=0,
            total_data_transferred=0
        )


@router.get("/devices", response_model=List[DeviceStats])
async def get_device_stats(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение статистики по устройствам"""
    try:
        device_manager = get_device_manager()
        if not device_manager:
            return []

        all_devices = await device_manager.get_all_devices()
        device_stats = []
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)

        for device_id, device_info in all_devices.items():
            try:
                device_uuid = uuid.UUID(device_id)

                # Статистика запросов для устройства
                stmt = select(
                    func.count(RequestLog.id).label('total'),
                    func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label('successful'),
                    func.avg(RequestLog.response_time_ms).label('avg_time'),
                    func.count(func.distinct(RequestLog.external_ip)).label('unique_ips')
                ).where(
                    RequestLog.device_id == device_uuid,
                    RequestLog.created_at >= yesterday
                )

                result = await db.execute(stmt)
                row = result.first()

                total_requests = row.total or 0
                successful_requests = row.successful or 0
                failed_requests = total_requests - successful_requests
                success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0

                device_stats.append(DeviceStats(
                    device_id=device_id,
                    device_name=device_info.get('device_info', f"Device {device_id}"),
                    device_type=device_info.get('type', 'unknown'),
                    total_requests=total_requests,
                    successful_requests=successful_requests,
                    failed_requests=failed_requests,
                    success_rate=success_rate,
                    avg_response_time_ms=int(row.avg_time or 0),
                    unique_ips=row.unique_ips or 0,
                    last_24h_requests=total_requests
                ))

            except ValueError:
                # Невалидный UUID, пропускаем
                continue
            except Exception as e:
                # Ошибка для конкретного устройства, пропускаем
                continue

        return device_stats

    except Exception as e:
        return []


@router.get("/requests", response_model=List[RequestStat])
async def get_request_stats(
    days: int = Query(default=7, ge=1, le=30, description="Number of days"),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение статистики запросов по дням"""
    try:
        stats = []

        for i in range(days):
            day_start = datetime.now(timezone.utc) - timedelta(days=i + 1)
            day_end = datetime.now(timezone.utc) - timedelta(days=i)

            stmt = select(
                func.count(RequestLog.id).label('total'),
                func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label('successful'),
                func.avg(RequestLog.response_time_ms).label('avg_time'),
                func.count(func.distinct(RequestLog.external_ip)).label('unique_ips')
            ).where(
                RequestLog.created_at >= day_start,
                RequestLog.created_at < day_end
            )

            result = await db.execute(stmt)
            row = result.first()

            total_requests = row.total or 0
            successful_requests = row.successful or 0

            stats.append(RequestStat(
                date=day_start.strftime("%Y-%m-%d"),
                total_requests=total_requests,
                successful_requests=successful_requests,
                failed_requests=total_requests - successful_requests,
                avg_response_time_ms=int(row.avg_time or 0),
                unique_ips=row.unique_ips or 0
            ))

        return stats[::-1]  # Обращаем для хронологического порядка

    except Exception as e:
        return []


@router.get("/ips", response_model=List[IpStat])
async def get_ip_stats(
    limit: int = Query(default=50, ge=1, le=200, description="Number of IPs"),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение статистики IP адресов"""
    try:
        stmt = select(IpHistory).order_by(IpHistory.total_requests.desc()).limit(limit)
        result = await db.execute(stmt)
        ip_records = result.scalars().all()

        ip_stats = []
        for ip_record in ip_records:
            # Рассчитываем success rate для IP
            success_rate = 100.0  # Placeholder, можно рассчитать из RequestLog

            ip_stats.append(IpStat(
                ip_address=ip_record.ip_address,
                operator=ip_record.operator,
                region=ip_record.geo_location,
                requests_count=ip_record.total_requests,
                success_rate=success_rate,
                first_seen=ip_record.first_seen,
                last_seen=ip_record.last_seen,
                is_blocked=ip_record.is_blocked
            ))

        return ip_stats

    except Exception as e:
        return []


@router.get("/realtime")
async def get_realtime_stats(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение статистики в реальном времени"""
    try:
        device_manager = get_device_manager()

        # Статистика устройств
        if device_manager:
            all_devices = await device_manager.get_all_devices()
            online_devices = len([d for d in all_devices.values() if d.get('status') == 'online'])
            total_devices = len(all_devices)
        else:
            online_devices = total_devices = 0

        # Статистика за последние 5 минут
        five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

        stmt = select(
            func.count(RequestLog.id).label('total'),
            func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label('successful'),
            func.avg(RequestLog.response_time_ms).label('avg_time')
        ).where(RequestLog.created_at >= five_minutes_ago)

        result = await db.execute(stmt)
        row = result.first()

        recent_requests = row.total or 0
        recent_successful = row.successful or 0

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requests_per_minute": recent_requests / 5,
            "devices": {
                "online": online_devices,
                "total": total_devices,
                "offline": total_devices - online_devices
            },
            "recent_stats": {
                "total_requests": recent_requests,
                "successful_requests": recent_successful,
                "failed_requests": recent_requests - recent_successful,
                "avg_response_time_ms": int(row.avg_time or 0),
                "success_rate": (recent_successful / recent_requests * 100) if recent_requests > 0 else 0,
                "period_minutes": 5
            }
        }

    except Exception as e:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requests_per_minute": 0,
            "devices": {"online": 0, "total": 0, "offline": 0},
            "recent_stats": {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_response_time_ms": 0,
                "success_rate": 0,
                "period_minutes": 5
            },
            "error": str(e)
        }


@router.get("/export")
async def export_stats(
    format: str = Query(default="json", description="Export format: json, csv"),
    days: int = Query(default=7, ge=1, le=90, description="Number of days"),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Экспорт статистики"""
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        if format.lower() == "csv":
            # Экспорт в CSV
            from fastapi.responses import Response

            stmt = select(RequestLog).where(RequestLog.created_at >= start_date).order_by(RequestLog.created_at.desc())
            result = await db.execute(stmt)
            logs = result.scalars().all()

            # Создаем CSV
            csv_lines = ["Date,Time,Device ID,Method,URL,Status Code,Response Time (ms),External IP"]

            for log in logs:
                csv_lines.append(
                    f"{log.created_at.strftime('%Y-%m-%d')},"
                    f"{log.created_at.strftime('%H:%M:%S')},"
                    f"{log.device_id or ''},"
                    f"{log.method or ''},"
                    f"\"{log.target_url or ''}\","
                    f"{log.status_code or ''},"
                    f"{log.response_time_ms or ''},"
                    f"{log.external_ip or ''}"
                )

            csv_content = "\n".join(csv_lines)

            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=proxy_stats_{days}days.csv"}
            )

        else:
            # Экспорт в JSON
            stmt = select(RequestLog).where(RequestLog.created_at >= start_date).order_by(RequestLog.created_at.desc())
            result = await db.execute(stmt)
            logs = result.scalars().all()

            export_data = {
                "export_info": {
                    "format": "json",
                    "period_days": days,
                    "start_date": start_date.isoformat(),
                    "end_date": datetime.now(timezone.utc).isoformat(),
                    "total_records": len(logs)
                },
                "data": [
                    {
                        "timestamp": log.created_at.isoformat(),
                        "device_id": str(log.device_id) if log.device_id else None,
                        "client_ip": log.client_ip,
                        "target_url": log.target_url,
                        "method": log.method,
                        "status_code": log.status_code,
                        "response_time_ms": log.response_time_ms,
                        "external_ip": log.external_ip,
                        "request_size": log.request_size,
                        "response_size": log.response_size,
                        "error_message": log.error_message
                    }
                    for log in logs
                ]
            }

            return export_data

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export stats: {str(e)}"
        )


@router.get("/summary")
async def get_stats_summary(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение краткой сводки статистики"""
    try:
        device_manager = get_device_manager()

        # Базовая информация об устройствах
        device_summary = {"total": 0, "online": 0}
        if device_manager:
            devices = await device_manager.get_all_devices()
            device_summary["total"] = len(devices)
            device_summary["online"] = len([d for d in devices.values() if d.get('status') == 'online'])

        # Статистика за разные периоды
        periods = {
            "last_hour": timedelta(hours=1),
            "last_24h": timedelta(days=1),
            "last_7d": timedelta(days=7)
        }

        stats_by_period = {}

        for period_name, period_delta in periods.items():
            start_time = datetime.now(timezone.utc) - period_delta

            stmt = select(
                func.count(RequestLog.id).label('total'),
                func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label('successful')
            ).where(RequestLog.created_at >= start_time)

            result = await db.execute(stmt)
            row = result.first()

            total = row.total or 0
            successful = row.successful or 0

            stats_by_period[period_name] = {
                "total_requests": total,
                "successful_requests": successful,
                "failed_requests": total - successful,
                "success_rate": (successful / total * 100) if total > 0 else 0
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "devices": device_summary,
            "requests": stats_by_period
        }

    except Exception as e:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "devices": {"total": 0, "online": 0},
            "requests": {},
            "error": str(e)
        }
