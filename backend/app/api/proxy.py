from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
import asyncio

from ..api.auth import get_current_active_user
from ..main import get_modem_manager, get_proxy_server, get_rotation_manager
from ..config import settings

router = APIRouter()


class ProxyInfo(BaseModel):
    host: str
    port: int
    protocol: str
    status: str
    total_modems: int
    online_modems: int
    max_connections: int
    timeout_seconds: int


class ModemInfo(BaseModel):
    id: str
    type: str
    interface: str
    status: str
    external_ip: Optional[str]
    last_rotation: Optional[datetime]
    requests_count: int
    success_rate: float


class ProxyStatus(BaseModel):
    proxy_server: ProxyInfo
    modems: List[ModemInfo]
    timestamp: datetime


class RotationRequest(BaseModel):
    modem_ids: Optional[List[str]] = None  # Если None, то все модемы
    force: bool = False


class RotationResult(BaseModel):
    success: bool
    message: str
    results: Dict[str, bool]  # modem_id -> success
    total_modems: int
    successful_rotations: int


@router.get("/status", response_model=ProxyStatus)
async def get_proxy_status(
        current_user=Depends(get_current_active_user)
):
    """Получение статуса прокси-сервера"""
    try:
        modem_manager = get_modem_manager()
        proxy_server = get_proxy_server()

        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        if not proxy_server:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Proxy server not available"
            )

        # Информация о прокси-сервере
        modems = await modem_manager.get_all_modems()
        online_modems = 0

        for modem_id in modems.keys():
            if await modem_manager.is_modem_online(modem_id):
                online_modems += 1

        proxy_info = ProxyInfo(
            host=settings.PROXY_HOST,
            port=settings.PROXY_PORT,
            protocol="http",
            status="running" if proxy_server.is_running() else "stopped",
            total_modems=len(modems),
            online_modems=online_modems,
            max_connections=settings.MAX_CONCURRENT_CONNECTIONS,
            timeout_seconds=settings.REQUEST_TIMEOUT_SECONDS
        )

        # Информация о модемах
        modem_infos = []
        for modem_id, modem_data in modems.items():
            external_ip = await modem_manager.get_modem_external_ip(modem_id)
            is_online = await modem_manager.is_modem_online(modem_id)

            modem_infos.append(ModemInfo(
                id=modem_id,
                type=modem_data['type'],
                interface=modem_data['interface'],
                status="online" if is_online else "offline",
                external_ip=external_ip,
                last_rotation=None,  # Можно добавить из БД
                requests_count=0,  # Можно добавить из БД
                success_rate=0.0  # Можно добавить из БД
            ))

        return ProxyStatus(
            proxy_server=proxy_info,
            modems=modem_infos,
            timestamp=datetime.now(timezone.utc)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get proxy status: {str(e)}"
        )


@router.get("/list")
async def get_proxy_list(
        current_user=Depends(get_current_active_user)
):
    """Получение списка доступных прокси"""
    try:
        modem_manager = get_modem_manager()

        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        modems = await modem_manager.get_all_modems()
        proxy_list = []

        for modem_id, modem_data in modems.items():
            is_online = await modem_manager.is_modem_online(modem_id)
            external_ip = await modem_manager.get_modem_external_ip(modem_id)

            if is_online:
                proxy_list.append({
                    "modem_id": modem_id,
                    "type": modem_data['type'],
                    "interface": modem_data['interface'],
                    "external_ip": external_ip,
                    "proxy_url": f"http://{settings.PROXY_HOST}:{settings.PROXY_PORT}",
                    "usage_header": "X-Proxy-Modem-ID",
                    "example_curl": f"curl -x http://{settings.PROXY_HOST}:{settings.PROXY_PORT} -H 'X-Proxy-Modem-ID: {modem_id}' https://httpbin.org/ip"
                })

        return {
            "total_proxies": len(proxy_list),
            "available_proxies": proxy_list,
            "proxy_server": {
                "host": settings.PROXY_HOST,
                "port": settings.PROXY_PORT,
                "protocol": "http"
            },
            "usage_instructions": {
                "random_proxy": f"curl -x http://{settings.PROXY_HOST}:{settings.PROXY_PORT} https://httpbin.org/ip",
                "specific_modem": f"curl -x http://{settings.PROXY_HOST}:{settings.PROXY_PORT} -H 'X-Proxy-Modem-ID: MODEM_ID' https://httpbin.org/ip"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get proxy list: {str(e)}"
        )


@router.get("/random")
async def get_random_proxy(
        current_user=Depends(get_current_active_user)
):
    """Получение случайного доступного прокси"""
    try:
        modem_manager = get_modem_manager()

        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        modems = await modem_manager.get_all_modems()
        available_modems = []

        for modem_id, modem_data in modems.items():
            if await modem_manager.is_modem_online(modem_id):
                available_modems.append({
                    "modem_id": modem_id,
                    "type": modem_data['type'],
                    "interface": modem_data['interface'],
                    "external_ip": await modem_manager.get_modem_external_ip(modem_id)
                })

        if not available_modems:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available modems"
            )

        import random
        selected_modem = random.choice(available_modems)

        return {
            "modem": selected_modem,
            "proxy_url": f"http://{settings.PROXY_HOST}:{settings.PROXY_PORT}",
            "usage_header": {
                "name": "X-Proxy-Modem-ID",
                "value": selected_modem["modem_id"]
            },
            "example_curl": f"curl -x http://{settings.PROXY_HOST}:{settings.PROXY_PORT} -H 'X-Proxy-Modem-ID: {selected_modem['modem_id']}' https://httpbin.org/ip"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get random proxy: {str(e)}"
        )


@router.post("/rotate", response_model=RotationResult)
async def rotate_proxy_ips(
        rotation_request: RotationRequest,
        current_user=Depends(get_current_active_user)
):
    """Ротация IP адресов прокси"""
    try:
        rotation_manager = get_rotation_manager()
        modem_manager = get_modem_manager()

        if not rotation_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rotation manager not available"
            )

        if not modem_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Modem manager not available"
            )

        # Определение модемов для ротации
        if rotation_request.modem_ids:
            target_modems = rotation_request.modem_ids
        else:
            # Все доступные модемы
            modems = await modem_manager.get_all_modems()
            target_modems = list(modems.keys())

        # Проверка доступности модемов
        available_modems = []
        for modem_id in target_modems:
            if await modem_manager.is_modem_online(modem_id):
                available_modems.append(modem_id)

        if not available_modems:
            return RotationResult(
                success=False,
                message="No available modems for rotation",
                results={},
                total_modems=0,
                successful_rotations=0
            )

        # Выполнение ротации
        results = {}

        if rotation_request.force:
            # Принудительная ротация всех модемов
            for modem_id in available_modems:
                success = await rotation_manager.rotate_modem_ip(modem_id)
                results[modem_id] = success
        else:
            # Ротация только онлайн модемов
            for modem_id in available_modems:
                success = await rotation_manager.rotate_modem_ip(modem_id)
                results[modem_id] = success

        successful_rotations = sum(1 for success in results.values() if success)
        total_modems = len(results)

        return RotationResult(
            success=successful_rotations > 0,
            message=f"Rotation completed: {successful_rotations}/{total_modems} modems rotated successfully",
            results=results,
            total_modems=total_modems,
            successful_rotations=successful_rotations
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate proxy IPs: {str(e)}"
        )


@router.get("/health")
async def get_proxy_health():
    """Проверка здоровья прокси-сервера (публичный эндпоинт)"""
    try:
        proxy_server = get_proxy_server()
        modem_manager = get_modem_manager()

        if not proxy_server:
            return {
                "status": "error",
                "message": "Proxy server not available",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        if not modem_manager:
            return {
                "status": "error",
                "message": "Modem manager not available",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        # Проверка доступности модемов
        modems = await modem_manager.get_all_modems()
        online_modems = 0

        for modem_id in modems.keys():
            if await modem_manager.is_modem_online(modem_id):
                online_modems += 1

        status = "healthy" if online_modems > 0 else "degraded"

        return {
            "status": status,
            "proxy_server": "running" if proxy_server.is_running() else "stopped",
            "total_modems": len(modems),
            "online_modems": online_modems,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/config")
async def get_proxy_config(
        current_user=Depends(get_current_active_user)
):
    """Получение конфигурации прокси-сервера"""
    try:
        return {
            "proxy_server": {
                "host": settings.PROXY_HOST,
                "port": settings.PROXY_PORT,
                "protocol": "http",
                "max_connections": settings.MAX_CONCURRENT_CONNECTIONS,
                "timeout_seconds": settings.REQUEST_TIMEOUT_SECONDS,
                "buffer_size": settings.BUFFER_SIZE
            },
            "rotation": {
                "default_interval": settings.DEFAULT_ROTATION_INTERVAL,
                "max_attempts": settings.MAX_ROTATION_ATTEMPTS,
                "timeout_seconds": settings.ROTATION_TIMEOUT_SECONDS,
                "retry_delay_seconds": settings.ROTATION_RETRY_DELAY_SECONDS
            },
            "limits": {
                "max_devices": settings.MAX_DEVICES,
                "max_requests_per_minute": settings.MAX_REQUESTS_PER_MINUTE
            },
            "monitoring": {
                "health_check_interval": settings.HEALTH_CHECK_INTERVAL,
                "heartbeat_timeout": settings.HEARTBEAT_TIMEOUT,
                "log_retention_days": settings.LOG_RETENTION_DAYS
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get proxy config: {str(e)}"
        )


@router.post("/test")
async def test_proxy(
        target_url: str = Query(default="https://httpbin.org/ip", description="URL to test"),
        modem_id: Optional[str] = Query(default=None, description="Specific modem to test"),
        current_user=Depends(get_current_active_user)
):
    """Тестирование прокси-сервера"""
    try:
        import aiohttp
        import time

        proxy_url = f"http://{settings.PROXY_HOST}:{settings.PROXY_PORT}"

        # Проверка доступности прокси-сервера
        proxy_server = get_proxy_server()
        if not proxy_server or not proxy_server.is_running():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Proxy server is not running"
            )

        # Подготовка заголовков
        headers = {}
        if modem_id:
            headers["X-Proxy-Modem-ID"] = modem_id

        start_time = time.time()

        # Выполнение тестового запроса
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                        target_url,
                        proxy=proxy_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                ) as response:

                    response_time = int((time.time() - start_time) * 1000)
                    response_text = await response.text()

                    # Попытка парсинга JSON ответа
                    try:
                        import json
                        response_data = json.loads(response_text)
                    except:
                        response_data = {"text": response_text[:500]}  # Первые 500 символов

                    return {
                        "success": True,
                        "status_code": response.status,
                        "response_time_ms": response_time,
                        "target_url": target_url,
                        "proxy_url": proxy_url,
                        "modem_id": modem_id,
                        "response_data": response_data,
                        "response_headers": dict(response.headers),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

            except aiohttp.ClientError as e:
                return {
                    "success": False,
                    "error": str(e),
                    "error_type": "client_error",
                    "target_url": target_url,
                    "proxy_url": proxy_url,
                    "modem_id": modem_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "error": "Request timeout",
                    "error_type": "timeout",
                    "target_url": target_url,
                    "proxy_url": proxy_url,
                    "modem_id": modem_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test proxy: {str(e)}"
        )


@router.get("/metrics")
async def get_proxy_metrics(
        current_user=Depends(get_current_active_user)
):
    """Получение метрик прокси-сервера"""
    try:
        from datetime import timedelta

        modem_manager = get_modem_manager()
        proxy_server = get_proxy_server()

        if not modem_manager or not proxy_server:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Services not available"
            )

        # Базовые метрики
        modems = await modem_manager.get_all_modems()
        online_modems = sum(1 for modem_id in modems.keys()
                            if await modem_manager.is_modem_online(modem_id))

        # Метрики за последний час
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        metrics = {
            "proxy_server": {
                "status": "running" if proxy_server.is_running() else "stopped",
                "uptime": "N/A",  # Можно добавить реальный uptime
                "host": settings.PROXY_HOST,
                "port": settings.PROXY_PORT
            },
            "modems": {
                "total": len(modems),
                "online": online_modems,
                "offline": len(modems) - online_modems,
                "utilization": (online_modems / len(modems) * 100) if modems else 0
            },
            "performance": {
                "requests_per_minute": 0,  # Можно добавить из БД
                "avg_response_time_ms": 0,  # Можно добавить из БД
                "error_rate": 0,  # Можно добавить из БД
                "success_rate": 0  # Можно добавить из БД
            },
            "resources": {
                "memory_usage": "N/A",
                "cpu_usage": "N/A",
                "connections": "N/A"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        return metrics

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get proxy metrics: {str(e)}"
        )


@router.post("/restart")
async def restart_proxy_server(
        current_user=Depends(get_current_active_user)
):
    """Перезапуск прокси-сервера"""
    try:
        proxy_server = get_proxy_server()

        if not proxy_server:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Proxy server not available"
            )

        # Остановка прокси-сервера
        await proxy_server.stop()

        # Небольшая пауза
        await asyncio.sleep(2)

        # Запуск прокси-сервера
        await proxy_server.start()

        return {
            "success": True,
            "message": "Proxy server restarted successfully",
            "status": "running" if proxy_server.is_running() else "stopped",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart proxy server: {str(e)}"
        )


@router.get("/usage-examples")
async def get_usage_examples(
        current_user=Depends(get_current_active_user)
):
    """Получение примеров использования прокси"""
    try:
        proxy_url = f"http://{settings.PROXY_HOST}:{settings.PROXY_PORT}"

        return {
            "basic_usage": {
                "description": "Базовое использование прокси",
                "examples": {
                    "curl": f"curl -x {proxy_url} https://httpbin.org/ip",
                    "python_requests": f"""
import requests

proxies = {{
    'http': '{proxy_url}',
    'https': '{proxy_url}'
}}

response = requests.get('https://httpbin.org/ip', proxies=proxies)
print(response.json())
""",
                    "javascript_fetch": f"""
// Для Node.js с библиотекой node-fetch
const fetch = require('node-fetch');
const HttpsProxyAgent = require('https-proxy-agent');

const agent = new HttpsProxyAgent('{proxy_url}');

fetch('https://httpbin.org/ip', {{ agent }})
    .then(response => response.json())
    .then(data => console.log(data));
"""
                }
            },
            "modem_selection": {
                "description": "Выбор конкретного модема",
                "examples": {
                    "curl": f"curl -x {proxy_url} -H 'X-Proxy-Modem-ID: your-modem-id' https://httpbin.org/ip",
                    "python_requests": f"""
import requests

proxies = {{
    'http': '{proxy_url}',
    'https': '{proxy_url}'
}}

headers = {{
    'X-Proxy-Modem-ID': 'your-modem-id'
}}

response = requests.get('https://httpbin.org/ip', proxies=proxies, headers=headers)
print(response.json())
""",
                    "javascript_fetch": f"""
const headers = {{
    'X-Proxy-Modem-ID': 'your-modem-id'
}};

fetch('https://httpbin.org/ip', {{ 
    agent,
    headers 
}})
    .then(response => response.json())
    .then(data => console.log(data));
"""
                }
            },
            "testing": {
                "description": "Тестирование прокси",
                "examples": {
                    "test_connection": f"curl -x {proxy_url} https://httpbin.org/ip",
                    "test_with_timeout": f"curl -x {proxy_url} --max-time 30 https://httpbin.org/ip",
                    "test_specific_modem": f"curl -x {proxy_url} -H 'X-Proxy-Modem-ID: modem-id' https://httpbin.org/ip"
                }
            },
            "configuration": {
                "description": "Настройка клиентов",
                "proxy_settings": {
                    "host": settings.PROXY_HOST,
                    "port": settings.PROXY_PORT,
                    "protocol": "http",
                    "authentication": "not_required"
                }
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage examples: {str(e)}"
        )