import random
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid

from ..models.database import get_db
from ..api.auth import get_current_active_user
from ..core.managers import get_device_manager, get_proxy_server

router = APIRouter()


class OverviewStats(BaseModel):
    total_modems: int
    online_modems: int
    offline_modems: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time: int  # ИСПРАВЛЕНО: убрал _ms
    unique_ips: int
    total_data_transferred: float  # ИСПРАВЛЕНО: изменил название


@router.get("/overview", response_model=OverviewStats)
async def get_overview_stats():
    """Получение общей статистики системы - БЕЗ АВТОРИЗАЦИИ ДЛЯ ОТЛАДКИ"""
    try:
        device_manager = get_device_manager()

        if device_manager:
            # Получаем реальные данные об устройствах
            all_devices = await device_manager.get_all_devices()
            total_modems = len(all_devices)
            online_modems = len([d for d in all_devices.values() if d.get('status') == 'online'])
            offline_modems = total_modems - online_modems
        else:
            total_modems = 0
            online_modems = 0
            offline_modems = 0

        # Возвращаем статистику (пока mock данные для запросов)
        total_requests = 3093
        successful_requests = 2876
        failed_requests = total_requests - successful_requests
        success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0

        return OverviewStats(
            total_modems=total_modems,
            online_modems=online_modems,
            offline_modems=offline_modems,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            success_rate=success_rate,
            avg_response_time=245,
            unique_ips=15,
            total_data_transferred=2.4
        )

    except Exception as e:
        # В случае ошибки возвращаем нулевую статистику
        return OverviewStats(
            total_modems=0,
            online_modems=0,
            offline_modems=0,
            total_requests=0,
            successful_requests=0,
            failed_requests=0,
            success_rate=0,
            avg_response_time=0,
            unique_ips=0,
            total_data_transferred=0
        )


@router.get("/requests")
async def get_request_stats(days: int = Query(default=7, description="Number of days")):
    """Получение статистики запросов по дням"""
    try:
        import random
        from datetime import datetime, timedelta

        # Генерируем mock данные
        data = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            data.append({
                "date": date.strftime("%Y-%m-%d"),
                "total_requests": random.randint(100, 500),
                "successful_requests": random.randint(80, 450),
                "failed_requests": random.randint(5, 50),
                "avg_response_time_ms": random.randint(200, 400),
                "unique_ips": random.randint(5, 20)
            })

        return {
            "data": data[::-1],  # Обращаем для хронологического порядка
            "total": len(data)
        }
    except Exception as e:
        return {"data": [], "total": 0}


@router.get("/ips")
async def get_ip_stats(limit: int = Query(default=10, description="Number of IPs")):
    """Получение статистики IP адресов"""
    try:
        import random

        # Генерируем mock данные
        mock_ips = []
        operators = ["МТС", "Билайн", "Мегафон", "Теле2"]

        for i in range(limit):
            mock_ips.append({
                "ip_address": f"192.168.1.{100 + i}",
                "operator": random.choice(operators),
                "requests_count": random.randint(50, 200),
                "success_rate": random.randint(85, 100)
            })

        return mock_ips
    except Exception as e:
        return []


@router.get("/realtime")
async def get_realtime_stats():
    """Получение статистики в реальном времени"""
    try:
        import random
        device_manager = get_device_manager()

        if device_manager:
            all_devices = await device_manager.get_all_devices()
            online_modems = len([d for d in all_devices.values() if d.get('status') == 'online'])
            total_modems = len(all_devices)
        else:
            online_modems = 0
            total_modems = 0

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requests_per_minute": random.randint(10, 50),
            "modems": {
                "online": online_modems,
                "total": total_modems,
                "offline": total_modems - online_modems
            },
            "recent_stats": {
                "total_requests": random.randint(20, 100),
                "successful_requests": random.randint(18, 95),
                "failed_requests": random.randint(2, 10),
                "avg_response_time_ms": random.randint(200, 400),
                "period_minutes": 5
            }
        }
    except Exception as e:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requests_per_minute": 0,
            "modems": {"online": 0, "total": 0, "offline": 0},
            "recent_stats": {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "avg_response_time_ms": 0,
                "period_minutes": 5
            }
        }


@router.get("/export")
async def export_stats(
    format: str = Query(default="csv", description="Export format"),
    days: int = Query(default=7, description="Number of days")
):
    """Экспорт статистики"""
    try:
        if format == "csv":
            # Генерируем CSV данные
            csv_data = "Date,Requests,Success Rate,Avg Response Time\n"
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                csv_data += f"{date},{random.randint(100, 500)},{random.randint(85, 100)},{random.randint(200, 400)}\n"

            return Response(
                content=csv_data,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=stats_{days}days.csv"}
            )
        else:
            return {"error": "Only CSV format supported"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
