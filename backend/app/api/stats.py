from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid

from ..models.database import get_db
from ..models.base import ProxyDevice, RequestLog, IpHistory, UsageStats
from ..api.auth import get_current_active_user
from ..core.managers import get_modem_manager, get_proxy_server, get_rotation_manager

router = APIRouter()


class OverviewStats(BaseModel):
    total_modems: int
    online_modems: int
    offline_modems: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time_ms: int
    unique_ips: int
    data_transferred_mb: int
    active_sessions: int


class ModemStats(BaseModel):
    modem_id: str
    modem_type: str
    interface: str
    status: str
    external_ip: Optional[str]
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time_ms: int
    unique_ips: int
    last_rotation: Optional[datetime]
    uptime_percentage: float


class RequestStatsItem(BaseModel):
    date: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: int
    unique_ips: int


class IpStatsItem(BaseModel):
    ip_address: str
    modem_id: str
    operator: Optional[str]
    geo_location: Optional[str]
    city: Optional[str]
    first_seen: datetime
    last_seen: datetime
    total_requests: int
    is_blocked: bool
    blocked_reason: Optional[str]


class RequestLogItem(BaseModel):
    id: str
    modem_id: Optional[str]
    client_ip: str
    target_url: str
    method: str
    status_code: int
    response_time_ms: int
    external_ip: Optional[str]
    created_at: datetime
    error_message: Optional[str]


@router.get("/overview", response_model=OverviewStats)
async def get_overview_stats(
        current_user=Depends(get_current_active_user),
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

        # Общая статистика запросов
        stmt = select(
            func.count(RequestLog.id),
            func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)),
            func.avg(RequestLog.response_time_ms),
            func.sum(RequestLog.request_size + RequestLog.response_size)
        )
        result = await db.execute(stmt)
        total_requests, successful_requests, avg_response_time, total_bytes = result.first()

        total_requests = total_requests or 0
        successful_requests = successful_requests or 0
        failed_requests = total_requests - successful_requests
        success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
        avg_response_time_ms = int(avg_response_time or 0)
        data_transferred_mb = int((total_bytes or 0) / (1024 * 1024))

        # Уникальные IP адреса
        stmt = select(func.count(func.distinct(IpHistory.ip_address)))
        result = await db.execute(stmt)
        unique_ips = result.scalar() or 0

        return OverviewStats(
            total_modems=len(modems),
            online_modems=online_modems,
            offline_modems=len(modems) - online_modems,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            success_rate=success_rate,
            avg_response_time_ms=avg_response_time_ms,
            unique_ips=unique_ips,
            data_transferred_mb=data_transferred_mb,
            active_sessions=0  # Заглушка для активных сессий
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get overview stats: {str(e)}"
        )


@router.get("/modems", response_model=List[ModemStats])
async def get_modems_stats(
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение статистики по модемам"""
    try:
        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        modems = await modem_manager.get_all_modems()
        modem_stats = []

        for modem_id, modem_info in modems.items():
            try:
                # Получение информации о модеме из БД
                device_uuid = uuid.UUID(modem_id)
                stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()

                # Статистика запросов для модема
                stmt = select(
                    func.count(RequestLog.id),
                    func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)),
                    func.avg(RequestLog.response_time_ms)
                ).where(RequestLog.device_id == device_uuid)
                result = await db.execute(stmt)
                total_requests, successful_requests, avg_response_time = result.first()

                total_requests = total_requests or 0
                successful_requests = successful_requests or 0
                failed_requests = total_requests - successful_requests
                success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0

                # Уникальные IP для модема
                stmt = select(func.count(func.distinct(IpHistory.ip_address))).where(
                    IpHistory.device_id == device_uuid
                )
                result = await db.execute(stmt)
                unique_ips = result.scalar() or 0

                # Статус и внешний IP
                is_online = await modem_manager.is_modem_online(modem_id)
                external_ip = await modem_manager.get_modem_external_ip(modem_id)

                modem_stats.append(ModemStats(
                    modem_id=modem_id,
                    modem_type=modem_info['type'],
                    interface=modem_info['interface'],
                    status="online" if is_online else "offline",
                    external_ip=external_ip,
                    total_requests=total_requests,
                    successful_requests=successful_requests,
                    failed_requests=failed_requests,
                    success_rate=success_rate,
                    avg_response_time_ms=int(avg_response_time or 0),
                    unique_ips=unique_ips,
                    last_rotation=device.last_ip_rotation if device else None,
                    uptime_percentage=95.0  # Заглушка для uptime
                ))

            except Exception as e:
                # Если не удается получить статистику для модема, добавляем базовую информацию
                modem_stats.append(ModemStats(
                    modem_id=modem_id,
                    modem_type=modem_info['type'],
                    interface=modem_info['interface'],
                    status="unknown",
                    external_ip=None,
                    total_requests=0,
                    successful_requests=0,
                    failed_requests=0,
                    success_rate=0.0,
                    avg_response_time_ms=0,
                    unique_ips=0,
                    last_rotation=None,
                    uptime_percentage=0.0
                ))

        return modem_stats

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get modems stats: {str(e)}"
        )


@router.get("/requests", response_model=List[RequestStatsItem])
async def get_request_stats(
        days: int = Query(default=7, description="Number of days to get stats for"),
        modem_id: Optional[str] = Query(default=None, description="Filter by modem ID"),
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение статистики запросов по дням"""
    try:
        if days > 90:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 90 days allowed"
            )

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)

        # Базовый запрос
        query = select(
            func.date(RequestLog.created_at).label('date'),
            func.count(RequestLog.id).label('total_requests'),
            func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)).label('successful_requests'),
            func.avg(RequestLog.response_time_ms).label('avg_response_time'),
            func.count(func.distinct(RequestLog.external_ip)).label('unique_ips')
        ).where(
            func.date(RequestLog.created_at).between(start_date, end_date)
        )

        # Фильтр по модему
        if modem_id:
            query = query.where(RequestLog.device_id == uuid.UUID(modem_id))

        query = query.group_by(func.date(RequestLog.created_at)).order_by(func.date(RequestLog.created_at))

        result = await db.execute(query)
        stats = result.all()

        stats_items = []
        for stat in stats:
            successful = stat.successful_requests or 0
            total = stat.total_requests or 0
            failed = total - successful

            stats_items.append(RequestStatsItem(
                date=stat.date.isoformat(),
                total_requests=total,
                successful_requests=successful,
                failed_requests=failed,
                avg_response_time_ms=int(stat.avg_response_time or 0),
                unique_ips=stat.unique_ips or 0
            ))

        return stats_items

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get request stats: {str(e)}"
        )


@router.get("/ips", response_model=List[IpStatsItem])
async def get_ip_stats(
        limit: int = Query(default=100, description="Number of IPs to return"),
        modem_id: Optional[str] = Query(default=None, description="Filter by modem ID"),
        blocked_only: bool = Query(default=False, description="Show only blocked IPs"),
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение статистики IP адресов"""
    try:
        query = select(IpHistory)

        if modem_id:
            query = query.where(IpHistory.device_id == uuid.UUID(modem_id))

        if blocked_only:
            query = query.where(IpHistory.is_blocked == True)

        query = query.order_by(IpHistory.last_seen.desc()).limit(limit)

        result = await db.execute(query)
        ip_history = result.scalars().all()

        ip_stats = []
        for ip_record in ip_history:
            ip_stats.append(IpStatsItem(
                ip_address=ip_record.ip_address,
                modem_id=str(ip_record.device_id),
                operator=ip_record.operator,
                geo_location=ip_record.geo_location,
                city=ip_record.city,
                first_seen=ip_record.first_seen,
                last_seen=ip_record.last_seen,
                total_requests=ip_record.total_requests,
                is_blocked=ip_record.is_blocked,
                blocked_reason=ip_record.blocked_reason
            ))

        return ip_stats

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get IP stats: {str(e)}"
        )


@router.get("/logs", response_model=List[RequestLogItem])
async def get_request_logs(
        limit: int = Query(default=100, description="Number of logs to return"),
        offset: int = Query(default=0, description="Offset for pagination"),
        modem_id: Optional[str] = Query(default=None, description="Filter by modem ID"),
        status_code: Optional[int] = Query(default=None, description="Filter by status code"),
        method: Optional[str] = Query(default=None, description="Filter by HTTP method"),
        client_ip: Optional[str] = Query(default=None, description="Filter by client IP"),
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение логов запросов"""
    try:
        query = select(RequestLog)

        # Применение фильтров
        if modem_id:
            query = query.where(RequestLog.device_id == uuid.UUID(modem_id))

        if status_code:
            query = query.where(RequestLog.status_code == status_code)

        if method:
            query = query.where(RequestLog.method == method.upper())

        if client_ip:
            query = query.where(RequestLog.client_ip == client_ip)

        query = query.order_by(RequestLog.created_at.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        logs = result.scalars().all()

        request_logs = []
        for log in logs:
            request_logs.append(RequestLogItem(
                id=str(log.id),
                modem_id=str(log.device_id) if log.device_id else None,
                client_ip=log.client_ip,
                target_url=log.target_url,
                method=log.method,
                status_code=log.status_code,
                response_time_ms=log.response_time_ms,
                external_ip=log.external_ip,
                created_at=log.created_at,
                error_message=log.error_message
            ))

        return request_logs

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get request logs: {str(e)}"
        )


@router.get("/export")
async def export_stats(
        format: str = Query(default="json", description="Export format: json or csv"),
        days: int = Query(default=7, description="Number of days to export"),
        modem_id: Optional[str] = Query(default=None, description="Filter by modem ID"),
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Экспорт статистики"""
    try:
        if format not in ["json", "csv"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Format must be 'json' or 'csv'"
            )

        if days > 90:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 90 days allowed"
            )

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Получение данных для экспорта
        query = select(RequestLog).where(
            RequestLog.created_at.between(start_date, end_date)
        )

        if modem_id:
            query = query.where(RequestLog.device_id == uuid.UUID(modem_id))

        query = query.order_by(RequestLog.created_at.desc())

        result = await db.execute(query)
        logs = result.scalars().all()

        # Подготовка данных
        export_data = []
        for log in logs:
            export_data.append({
                "id": str(log.id),
                "modem_id": str(log.device_id) if log.device_id else None,
                "client_ip": log.client_ip,
                "target_url": log.target_url,
                "method": log.method,
                "status_code": log.status_code,
                "response_time_ms": log.response_time_ms,
                "external_ip": log.external_ip,
                "user_agent": log.user_agent,
                "request_size": log.request_size,
                "response_size": log.response_size,
                "created_at": log.created_at.isoformat(),
                "error_message": log.error_message
            })

        if format == "json":
            from fastapi.responses import JSONResponse
            return JSONResponse(
                content={
                    "export_date": datetime.now(timezone.utc).isoformat(),
                    "period_days": days,
                    "modem_id": modem_id,
                    "total_records": len(export_data),
                    "data": export_data
                }
            )

        elif format == "csv":
            import csv
            from io import StringIO
            from fastapi.responses import StreamingResponse

            output = StringIO()

            if export_data:
                writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
                writer.writeheader()
                writer.writerows(export_data)

            output.seek(0)

            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=stats_export_{days}days.csv"}
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export stats: {str(e)}"
        )


@router.get("/realtime")
async def get_realtime_stats(
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение статистики в реальном времени"""
    try:
        modem_manager = get_modem_manager()
        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Статистика за последние 5 минут
        five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Запросы за последние 5 минут
        stmt = select(
            func.count(RequestLog.id),
            func.sum(func.case((RequestLog.status_code.between(200, 299), 1), else_=0)),
            func.avg(RequestLog.response_time_ms)
        ).where(RequestLog.created_at >= five_minutes_ago)

        result = await db.execute(stmt)
        recent_total, recent_successful, recent_avg_time = result.first()

        recent_total = recent_total or 0
        recent_successful = recent_successful or 0
        recent_failed = recent_total - recent_successful

        # Статус модемов
        modems = await modem_manager.get_all_modems()
        online_modems = 0

        for modem_id in modems.keys():
            if await modem_manager.is_modem_online(modem_id):
                online_modems += 1

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recent_stats": {
                "total_requests": recent_total,
                "successful_requests": recent_successful,
                "failed_requests": recent_failed,
                "avg_response_time_ms": int(recent_avg_time or 0),
                "period_minutes": 5
            },
            "modems": {
                "total": len(modems),
                "online": online_modems,
                "offline": len(modems) - online_modems
            },
            "requests_per_minute": recent_total / 5 if recent_total > 0 else 0
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get realtime stats: {str(e)}"
        )
