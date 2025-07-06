# backend/app/api/proxy.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import asyncio
import aiohttp
import time

from ..api.auth import get_current_active_user
from ..core.managers import get_device_manager, get_proxy_server
from ..config import settings

router = APIRouter()

class ProxyInfo(BaseModel):
    host: str
    port: int
    protocol: str
    status: str
    total_devices: int
    online_devices: int
    max_connections: int
    timeout_seconds: int

class DeviceInfo(BaseModel):
    id: str
    type: str
    interface: str
    status: str
    external_ip: Optional[str]
    routing_capable: bool
    usb_interface: Optional[str]

class ProxyStatus(BaseModel):
    proxy_server: ProxyInfo
    devices: List[DeviceInfo]
    timestamp: datetime

class RotationRequest(BaseModel):
    device_ids: Optional[List[str]] = None
    force: bool = False

class RotationResult(BaseModel):
    success: bool
    message: str
    results: Dict[str, bool]
    total_devices: int
    successful_rotations: int

@router.get("/status", response_model=ProxyStatus)
async def get_proxy_status(current_user=Depends(get_current_active_user)):
    """Получение статуса прокси-сервера"""
    try:
        device_manager = get_device_manager()
        proxy_server = get_proxy_server()

        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        if not proxy_server:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Proxy server not available"
            )

        # Получаем информацию об устройствах
        all_devices = await device_manager.get_all_devices()
        online_devices = 0
        device_infos = []

        for device_id, device_data in all_devices.items():
            is_online = await device_manager.is_device_online(device_id)
            if is_online:
                online_devices += 1

            external_ip = await device_manager.get_device_external_ip(device_id)

            device_infos.append(DeviceInfo(
                id=device_id,
                type=device_data.get('type', 'unknown'),
                interface=device_data.get('interface', 'unknown'),
                status="online" if is_online else "offline",
                external_ip=external_ip,
                routing_capable=device_data.get('routing_capable', False),
                usb_interface=device_data.get('usb_interface')
            ))

        # Информация о прокси-сервере
        proxy_info = ProxyInfo(
            host=settings.proxy_host,
            port=settings.proxy_port,
            protocol="http",
            status="running" if proxy_server.is_running() else "stopped",
            total_devices=len(all_devices),
            online_devices=online_devices,
            max_connections=settings.max_concurrent_connections,
            timeout_seconds=settings.request_timeout_seconds
        )

        return ProxyStatus(
            proxy_server=proxy_info,
            devices=device_infos,
            timestamp=datetime.now(timezone.utc)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get proxy status: {str(e)}"
        )

@router.get("/health")
async def get_proxy_health():
    """Проверка здоровья прокси-сервера (публичный эндпоинт)"""
    try:
        proxy_server = get_proxy_server()
        device_manager = get_device_manager()

        if not proxy_server:
            return {
                "status": "error",
                "message": "Proxy server not available",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        if not device_manager:
            return {
                "status": "error",
                "message": "Device manager not available",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        # Проверка доступности устройств
        devices = await device_manager.get_all_devices()
        online_devices = 0

        for device_id in devices.keys():
            if await device_manager.is_device_online(device_id):
                online_devices += 1

        status_result = "healthy" if online_devices > 0 else "degraded"

        return {
            "status": status_result,
            "proxy_server": "running" if proxy_server.is_running() else "stopped",
            "total_devices": len(devices),
            "online_devices": online_devices,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@router.get("/list")
async def get_proxy_list(current_user=Depends(get_current_active_user)):
    """Получение списка доступных прокси"""
    try:
        device_manager = get_device_manager()

        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        devices = await device_manager.get_all_devices()
        proxy_list = []

        for device_id, device_data in devices.items():
            is_online = await device_manager.is_device_online(device_id)
            external_ip = await device_manager.get_device_external_ip(device_id)

            if is_online:
                proxy_list.append({
                    "device_id": device_id,
                    "type": device_data.get('type', 'unknown'),
                    "interface": device_data.get('interface', 'unknown'),
                    "usb_interface": device_data.get('usb_interface'),
                    "external_ip": external_ip,
                    "proxy_url": f"http://{settings.proxy_host}:{settings.proxy_port}",
                    "usage_header": "X-Proxy-Device-ID",
                    "example_curl": f"curl -x http://{settings.proxy_host}:{settings.proxy_port} -H 'X-Proxy-Device-ID: {device_id}' https://httpbin.org/ip"
                })

        return {
            "total_proxies": len(proxy_list),
            "available_proxies": proxy_list,
            "proxy_server": {
                "host": settings.proxy_host,
                "port": settings.proxy_port,
                "protocol": "http"
            },
            "usage_instructions": {
                "random_device": f"curl -x http://{settings.proxy_host}:{settings.proxy_port} https://httpbin.org/ip",
                "specific_device": f"curl -x http://{settings.proxy_host}:{settings.proxy_port} -H 'X-Proxy-Device-ID: DEVICE_ID' https://httpbin.org/ip"
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
async def get_random_proxy(current_user=Depends(get_current_active_user)):
    """Получение случайного доступного прокси"""
    try:
        device_manager = get_device_manager()

        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        devices = await device_manager.get_all_devices()
        available_devices = []

        for device_id, device_data in devices.items():
            if await device_manager.is_device_online(device_id):
                available_devices.append({
                    "device_id": device_id,
                    "type": device_data.get('type', 'unknown'),
                    "interface": device_data.get('interface', 'unknown'),
                    "external_ip": await device_manager.get_device_external_ip(device_id)
                })

        if not available_devices:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available devices"
            )

        import random
        selected_device = random.choice(available_devices)

        return {
            "device": selected_device,
            "proxy_url": f"http://{settings.proxy_host}:{settings.proxy_port}",
            "usage_header": {
                "name": "X-Proxy-Device-ID",
                "value": selected_device["device_id"]
            },
            "example_curl": f"curl -x http://{settings.proxy_host}:{settings.proxy_port} -H 'X-Proxy-Device-ID: {selected_device['device_id']}' https://httpbin.org/ip"
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
        device_manager = get_device_manager()

        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        # Определение устройств для ротации
        if rotation_request.device_ids:
            target_devices = rotation_request.device_ids
        else:
            # Все доступные устройства
            devices = await device_manager.get_all_devices()
            target_devices = list(devices.keys())

        # Проверка доступности устройств
        available_devices = []
        for device_id in target_devices:
            if await device_manager.is_device_online(device_id):
                available_devices.append(device_id)

        if not available_devices:
            return RotationResult(
                success=False,
                message="No available devices for rotation",
                results={},
                total_devices=0,
                successful_rotations=0
            )

        # Выполнение ротации
        results = {}

        for device_id in available_devices:
            success = await device_manager.rotate_device_ip(device_id)
            results[device_id] = success

        successful_rotations = sum(1 for success in results.values() if success)
        total_devices = len(results)

        return RotationResult(
            success=successful_rotations > 0,
            message=f"Rotation completed: {successful_rotations}/{total_devices} devices rotated successfully",
            results=results,
            total_devices=total_devices,
            successful_rotations=successful_rotations
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate proxy IPs: {str(e)}"
        )

@router.get("/config")
async def get_proxy_config(current_user=Depends(get_current_active_user)):
    """Получение конфигурации прокси-сервера"""
    try:
        return {
            "proxy_server": {
                "host": settings.proxy_host,
                "port": settings.proxy_port,
                "protocol": "http",
                "max_connections": settings.max_concurrent_connections,
                "timeout_seconds": settings.request_timeout_seconds
            },
            "rotation": {
                "default_interval": settings.default_rotation_interval,
                "max_attempts": getattr(settings, 'max_rotation_attempts', 3),
                "timeout_seconds": getattr(settings, 'rotation_timeout_seconds', 60)
            },
            "limits": {
                "max_devices": settings.max_devices,
                "max_requests_per_minute": settings.max_requests_per_minute
            },
            "monitoring": {
                "health_check_interval": settings.health_check_interval,
                "heartbeat_timeout": settings.heartbeat_timeout
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get proxy config: {str(e)}"
        )

@router.post("/test")
async def test_proxy(
    target_url: str = Query(default="http://httpbin.org/ip", description="URL to test"),
    device_id: Optional[str] = Query(default=None, description="Specific device to test")
):
    """Тестирование прокси-сервера через устройства"""
    try:
        device_manager = get_device_manager()
        proxy_server = get_proxy_server()

        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        if not proxy_server:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Proxy server not available"
            )

        if not proxy_server.is_running():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Proxy server is not running"
            )

        # Проверяем устройства
        all_devices = await device_manager.get_all_devices()

        if device_id and device_id not in all_devices:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        if not all_devices:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No devices available"
            )

        # Настройка прокси URL
        proxy_url = f"http://{settings.proxy_host}:{settings.proxy_port}"
        if settings.proxy_host == "0.0.0.0":
            proxy_url = f"http://127.0.0.1:{settings.proxy_port}"

        # Подготовка заголовков
        headers = {'User-Agent': 'Mobile-Proxy-Test/1.0'}
        if device_id:
            headers["X-Proxy-Device-ID"] = device_id

        start_time = time.time()

        try:
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    target_url,
                    proxy=proxy_url,
                    headers=headers
                ) as response:
                    response_time = int((time.time() - start_time) * 1000)
                    response_data = await response.text()

                    success = 200 <= response.status < 400

                    return {
                        "success": success,
                        "status_code": response.status,
                        "response_time_ms": response_time,
                        "target_url": target_url,
                        "proxy_url": proxy_url,
                        "device_id": device_id,
                        "response_data": response_data[:500] if len(response_data) > 500 else response_data,
                        "test_details": {
                            "proxy_connection": "successful" if success else "failed",
                            "proxy_host": settings.proxy_host,
                            "proxy_port": settings.proxy_port,
                            "headers_sent": dict(headers)
                        },
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

        except aiohttp.ClientError as e:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "error": str(e),
                "error_type": "client_error",
                "response_time_ms": response_time,
                "target_url": target_url,
                "proxy_url": proxy_url,
                "device_id": device_id,
                "test_details": {
                    "proxy_connection": "failed",
                    "error_detail": str(e)
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except asyncio.TimeoutError:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "error": "Request timeout",
                "error_type": "timeout",
                "response_time_ms": response_time,
                "target_url": target_url,
                "proxy_url": proxy_url,
                "device_id": device_id,
                "test_details": {
                    "proxy_connection": "timeout"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test proxy: {str(e)}"
        )

@router.post("/restart")
async def restart_proxy_server(current_user=Depends(get_current_active_user)):
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
async def get_usage_examples(current_user=Depends(get_current_active_user)):
    """Получение примеров использования прокси"""
    try:
        proxy_url = f"http://{settings.proxy_host}:{settings.proxy_port}"

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
            "device_selection": {
                "description": "Выбор конкретного устройства",
                "examples": {
                    "curl": f"curl -x {proxy_url} -H 'X-Proxy-Device-ID: your-device-id' https://httpbin.org/ip",
                    "python_requests": f"""
import requests

proxies = {{
    'http': '{proxy_url}',
    'https': '{proxy_url}'
}}

headers = {{
    'X-Proxy-Device-ID': 'your-device-id'
}}

response = requests.get('https://httpbin.org/ip', proxies=proxies, headers=headers)
print(response.json())
"""
                }
            },
            "testing": {
                "description": "Тестирование прокси",
                "examples": {
                    "test_connection": f"curl -x {proxy_url} https://httpbin.org/ip",
                    "test_with_timeout": f"curl -x {proxy_url} --max-time 30 https://httpbin.org/ip",
                    "test_specific_device": f"curl -x {proxy_url} -H 'X-Proxy-Device-ID: device-id' https://httpbin.org/ip"
                }
            },
            "configuration": {
                "description": "Настройка клиентов",
                "proxy_settings": {
                    "host": settings.proxy_host,
                    "port": settings.proxy_port,
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

@router.get("/metrics")
async def get_proxy_metrics(current_user=Depends(get_current_active_user)):
    """Получение метрик прокси-сервера"""
    try:
        from datetime import timedelta

        device_manager = get_device_manager()
        proxy_server = get_proxy_server()

        if not device_manager or not proxy_server:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Services not available"
            )

        # Базовые метрики
        devices = await device_manager.get_all_devices()
        online_devices = sum(1 for device_id in devices.keys()
                            if await device_manager.is_device_online(device_id))

        # Метрики за последний час
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        metrics = {
            "proxy_server": {
                "status": "running" if proxy_server.is_running() else "stopped",
                "uptime": "N/A",  # Можно добавить реальный uptime
                "host": settings.proxy_host,
                "port": settings.proxy_port
            },
            "devices": {
                "total": len(devices),
                "online": online_devices,
                "offline": len(devices) - online_devices,
                "utilization": (online_devices / len(devices) * 100) if devices else 0
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
