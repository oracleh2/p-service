# backend/app/api/dedicated_proxy.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from ..models.database import get_db
from ..api.auth import get_admin_user, get_current_active_user
from ..core.managers import get_device_manager, get_dedicated_proxy_manager
import structlog
from pydantic import BaseModel, validator

router = APIRouter()
logger = structlog.get_logger()

class DedicatedProxyRequest(BaseModel):
    device_id: str
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None

    # Добавляем валидацию порта
    @validator('port')
    def validate_port(cls, v):
        if v is not None:
            if not (6000 <= v <= 7000):
                raise ValueError('Port must be between 6000 and 7000')
        return v

class DedicatedProxyUpdateRequest(BaseModel):
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None

    @validator('port')
    def validate_port(cls, v):
        if v is not None:
            if not (6000 <= v <= 7000):
                raise ValueError('Port must be between 6000 and 7000')
        return v

class DedicatedProxyResponse(BaseModel):
    device_id: str
    port: int
    username: str
    password: str
    proxy_url: str
    status: str
    device_name: Optional[str] = None
    device_status: Optional[str] = None
    created_at: Optional[datetime] = None


class DedicatedProxyListResponse(BaseModel):
    proxies: List[DedicatedProxyResponse]
    total_count: int
    active_count: int


@router.post("/create", response_model=DedicatedProxyResponse)
async def create_dedicated_proxy(
    request: DedicatedProxyRequest,
    current_user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Создание индивидуального прокси для устройства"""
    try:
        device_manager = get_device_manager()
        dedicated_proxy_manager = get_dedicated_proxy_manager()

        if not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device manager not available"
            )

        if not dedicated_proxy_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dedicated proxy manager not available"
            )

        # Проверка существования устройства
        device = await device_manager.get_device_by_id(request.device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        # Проверка, что у устройства еще нет индивидуального прокси
        existing_proxy = await dedicated_proxy_manager.get_device_proxy_info(request.device_id)
        if existing_proxy:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Device already has dedicated proxy"
            )

        # Создание индивидуального прокси
        proxy_info = await dedicated_proxy_manager.create_dedicated_proxy(
            device_id=request.device_id,
            port=request.port,
            username=request.username,
            password=request.password
        )

        # ИСПРАВЛЕНО: Правильная обработка данных устройства
        device_name = None
        device_status = None

        if device:
            # Пробуем разные возможные ключи для имени устройства
            device_name = (device.get("device_info") or
                           device.get("name") or
                           device.get("device_name") or
                           f"Device {request.device_id}")

            # Пробуем разные возможные ключи для статуса
            device_status = (device.get("status") or
                             device.get("device_status") or
                             "unknown")

        return DedicatedProxyResponse(
            device_id=proxy_info["device_id"],
            port=proxy_info["port"],
            username=proxy_info["username"],
            password=proxy_info["password"],
            proxy_url=proxy_info["proxy_url"],
            status=proxy_info["status"],
            device_name=device_name,
            device_status=device_status
        )

    except HTTPException:
        raise
    except Exception as e:
        # ИСПРАВЛЕНО: Добавляем детальное логирование ошибки
        import traceback
        error_details = traceback.format_exc()

        # Логируем полную ошибку для диагностики
        logger.error(f"Failed to create dedicated proxy: {str(e)}")
        logger.error(f"Full traceback: {error_details}")
        logger.error(f"Request data: device_id={request.device_id}, port={request.port}")
        logger.error(f"Device data: {device if 'device' in locals() else 'Not retrieved'}")
        logger.error(f"Proxy info: {proxy_info if 'proxy_info' in locals() else 'Not created'}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create dedicated proxy: {str(e)}"
        )

@router.put("/{device_id}/update", response_model=DedicatedProxyResponse)
async def update_dedicated_proxy(
    device_id: str,
    request: DedicatedProxyUpdateRequest,
    current_user=Depends(get_admin_user)
):
    """Обновление конфигурации индивидуального прокси"""
    try:
        dedicated_proxy_manager = get_dedicated_proxy_manager()
        device_manager = get_device_manager()

        if not dedicated_proxy_manager or not device_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Required managers not available"
            )

        # Проверка существования прокси
        existing_proxy = await dedicated_proxy_manager.get_device_proxy_info(device_id)
        if not existing_proxy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dedicated proxy not found for this device"
            )

        # Подготовка новых параметров
        new_port = request.port if request.port is not None else existing_proxy["port"]
        new_username = request.username if request.username else existing_proxy["username"]
        new_password = request.password if request.password else existing_proxy["password"]

        # Проверка уникальности нового порта (если он изменился)
        if new_port != existing_proxy["port"]:
            if not await dedicated_proxy_manager.is_port_available(new_port):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Port {new_port} is already in use"
                )

        # Удаление старого прокси
        await dedicated_proxy_manager.remove_dedicated_proxy(device_id)

        # Создание нового с обновленными параметрами
        updated_proxy = await dedicated_proxy_manager.create_dedicated_proxy(
            device_id=device_id,
            port=new_port,
            username=new_username,
            password=new_password
        )

        # Получение информации об устройстве
        device = await device_manager.get_device_by_id(device_id)

        return DedicatedProxyResponse(
            device_id=updated_proxy["device_id"],
            port=updated_proxy["port"],
            username=updated_proxy["username"],
            password=updated_proxy["password"],
            proxy_url=updated_proxy["proxy_url"],
            status=updated_proxy["status"],
            device_name=device.get("device_info") if device else "Unknown",
            device_status=device.get("status") if device else "offline"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update dedicated proxy: {str(e)}"
        )

@router.delete("/{device_id}")
async def remove_dedicated_proxy(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Удаление индивидуального прокси для устройства"""
    try:
        dedicated_proxy_manager = get_dedicated_proxy_manager()

        if not dedicated_proxy_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dedicated proxy manager not available"
            )

        # Проверка существования прокси
        proxy_info = await dedicated_proxy_manager.get_device_proxy_info(device_id)
        if not proxy_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dedicated proxy not found for this device"
            )

        # Удаление прокси
        await dedicated_proxy_manager.remove_dedicated_proxy(device_id)

        return {
            "message": "Dedicated proxy removed successfully",
            "device_id": device_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove dedicated proxy: {str(e)}"
        )


@router.get("/list", response_model=DedicatedProxyListResponse)
async def list_dedicated_proxies(
    current_user=Depends(get_current_active_user)
):
    """Список всех индивидуальных прокси"""
    try:
        device_manager = get_device_manager()
        dedicated_proxy_manager = get_dedicated_proxy_manager()

        if not device_manager or not dedicated_proxy_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Required managers not available"
            )

        # Получение списка прокси
        proxies_info = await dedicated_proxy_manager.list_all_dedicated_proxies()

        # Обогащение информацией об устройствах
        enriched_proxies = []
        active_count = 0

        for proxy_info in proxies_info:
            device = await device_manager.get_device_by_id(proxy_info["device_id"])

            proxy_response = DedicatedProxyResponse(
                device_id=proxy_info["device_id"],
                port=proxy_info["port"],
                username=proxy_info["username"],
                password=proxy_info["password"],
                proxy_url=proxy_info["proxy_url"],
                status=proxy_info["status"],
                device_name=device.get("name") if device else "Unknown",
                device_status=device.get("status") if device else "offline"
            )

            enriched_proxies.append(proxy_response)

            if proxy_info["status"] == "running":
                active_count += 1

        return DedicatedProxyListResponse(
            proxies=enriched_proxies,
            total_count=len(enriched_proxies),
            active_count=active_count
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list dedicated proxies: {str(e)}"
        )


@router.get("/{device_id}", response_model=DedicatedProxyResponse)
async def get_dedicated_proxy_info(
    device_id: str,
    current_user=Depends(get_current_active_user)
):
    """Получение информации об индивидуальном прокси устройства"""
    try:
        device_manager = get_device_manager()
        dedicated_proxy_manager = get_dedicated_proxy_manager()

        if not device_manager or not dedicated_proxy_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Required managers not available"
            )

        # Получение информации о прокси
        proxy_info = await dedicated_proxy_manager.get_device_proxy_info(device_id)
        if not proxy_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dedicated proxy not found for this device"
            )

        # Получение информации об устройстве
        device = await device_manager.get_device_by_id(device_id)

        return DedicatedProxyResponse(
            device_id=proxy_info["device_id"],
            port=proxy_info["port"],
            username=proxy_info["username"],
            password=proxy_info["password"],
            proxy_url=proxy_info["proxy_url"],
            status=proxy_info["status"],
            device_name=device.get("name") if device else "Unknown",
            device_status=device.get("status") if device else "offline"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dedicated proxy info: {str(e)}"
        )


@router.post("/{device_id}/regenerate-credentials")
async def regenerate_proxy_credentials(
    device_id: str,
    current_user=Depends(get_admin_user)
):
    """Перегенерация учетных данных для индивидуального прокси"""
    try:
        dedicated_proxy_manager = get_dedicated_proxy_manager()

        if not dedicated_proxy_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dedicated proxy manager not available"
            )

        # Проверка существования прокси
        proxy_info = await dedicated_proxy_manager.get_device_proxy_info(device_id)
        if not proxy_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dedicated proxy not found for this device"
            )

        # Удаление старого прокси
        await dedicated_proxy_manager.remove_dedicated_proxy(device_id)

        # Создание нового с теми же параметрами, но новыми учетными данными
        import secrets
        new_username = f"device_{device_id[:8]}_{secrets.token_hex(4)}"
        new_password = secrets.token_urlsafe(16)

        new_proxy_info = await dedicated_proxy_manager.create_dedicated_proxy(
            device_id=device_id,
            port=proxy_info["port"],  # Сохраняем тот же порт
            username=new_username,
            password=new_password
        )

        return {
            "message": "Credentials regenerated successfully",
            "device_id": device_id,
            "new_username": new_username,
            "new_password": new_password,
            "proxy_url": new_proxy_info["proxy_url"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate credentials: {str(e)}"
        )


@router.get("/usage/{device_id}/examples")
async def get_usage_examples(
    device_id: str,
    current_user=Depends(get_current_active_user)
):
    """Получение примеров использования индивидуального прокси"""
    try:
        dedicated_proxy_manager = get_dedicated_proxy_manager()

        if not dedicated_proxy_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Dedicated proxy manager not available"
            )

        # Получение информации о прокси
        proxy_info = await dedicated_proxy_manager.get_device_proxy_info(device_id)
        if not proxy_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dedicated proxy not found for this device"
            )

        # Формирование URL прокси
        proxy_url = f"http://{proxy_info['username']}:{proxy_info['password']}@192.168.1.50:{proxy_info['port']}"
        proxy_url_without_auth = f"http://192.168.1.50:{proxy_info['port']}"

        return {
            "device_id": device_id,
            "proxy_info": {
                "host": "192.168.1.50",
                "port": proxy_info["port"],
                "username": proxy_info["username"],
                "password": proxy_info["password"],
                "url": proxy_url,
                "url_without_auth": proxy_url_without_auth
            },
            "usage_examples": {
                "curl_check_ip": {
                    "description": "Проверка внешнего IP через прокси",
                    "example": f"curl -x {proxy_url} https://httpbin.org/ip"
                },
                "curl_with_auth_header": {
                    "description": "Использование cURL с заголовком авторизации",
                    "example": f"""curl -x {proxy_url_without_auth} \\
  -H "Proxy-Authorization: Basic $(echo -n '{proxy_info['username']}:{proxy_info['password']}' | base64)" \\
  https://httpbin.org/ip"""
                },
                "curl_user_agent": {
                    "description": "Проверка User-Agent через прокси",
                    "example": f"curl -x {proxy_url} -A 'MyBot/1.0' https://httpbin.org/user-agent"
                },
                "curl_headers": {
                    "description": "Проверка всех заголовков",
                    "example": f"curl -x {proxy_url} https://httpbin.org/headers"
                },
                "python_requests": {
                    "description": "Использование через Python requests",
                    "example": f"""import requests

proxies = {{
    'http': '{proxy_url}',
    'https': '{proxy_url}'
}}

# Проверка IP
response = requests.get('https://httpbin.org/ip', proxies=proxies)
print(response.json())

# Проверка с кастомными заголовками
headers = {{'User-Agent': 'MyBot/1.0'}}
response = requests.get('https://httpbin.org/headers',
                       proxies=proxies, headers=headers)
print(response.json())"""
                },
                "javascript_node": {
                    "description": "Использование через Node.js",
                    "example": f"""const fetch = require('node-fetch');
const HttpsProxyAgent = require('https-proxy-agent');

const agent = new HttpsProxyAgent('{proxy_url}');

// Проверка IP
fetch('https://httpbin.org/ip', {{ agent }})
    .then(response => response.json())
    .then(data => console.log('IP:', data));

// Проверка с заголовками
fetch('https://httpbin.org/headers', {{
    agent,
    headers: {{ 'User-Agent': 'MyBot/1.0' }}
}})
    .then(response => response.json())
    .then(data => console.log('Headers:', data));"""
                },
                "browser_config": {
                    "description": "Настройка браузера",
                    "example": {
                        "host": "192.168.1.50",
                        "port": proxy_info["port"],
                        "username": proxy_info["username"],
                        "password": proxy_info["password"],
                        "type": "HTTP",
                        "note": "Включите аутентификацию прокси в настройках браузера"
                    }
                },
                "wget": {
                    "description": "Использование wget",
                    "example": f"""# Настройка через переменные окружения
export http_proxy='{proxy_url}'
export https_proxy='{proxy_url}'
wget https://httpbin.org/ip

# Или напрямую
wget --proxy-user='{proxy_info['username']}' \\
     --proxy-password='{proxy_info['password']}' \\
     --proxy=on \\
     -e use_proxy=yes \\
     -e http_proxy=192.168.1.50:{proxy_info['port']} \\
     https://httpbin.org/ip"""
                },
                "php": {
                    "description": "Использование через PHP",
                    "example": f"""<?php
$context = stream_context_create([
    'http' => [
        'proxy' => 'tcp://192.168.1.50:{proxy_info["port"]}',
        'request_fulluri' => true,
        'header' => [
            'Proxy-Authorization: Basic ' . base64_encode('{proxy_info["username"]}:{proxy_info["password"]}')
        ]
    ]
]);

$response = file_get_contents('https://httpbin.org/ip', false, $context);
echo $response;
?>"""
                },
                "testing_commands": {
                    "description": "Команды для тестирования прокси",
                    "examples": [
                        {
                            "name": "Проверка IP",
                            "command": f"curl -x {proxy_url} https://httpbin.org/ip"
                        },
                        {
                            "name": "Проверка скорости",
                            "command": f"curl -x {proxy_url} -w '%{{time_total}}' -o /dev/null -s https://httpbin.org/delay/1"
                        },
                        {
                            "name": "Проверка HTTPS",
                            "command": f"curl -x {proxy_url} https://httpbin.org/get"
                        },
                        {
                            "name": "Проверка User-Agent",
                            "command": f"curl -x {proxy_url} -A 'Test-Agent' https://httpbin.org/user-agent"
                        },
                        {
                            "name": "Проверка заголовков",
                            "command": f"curl -x {proxy_url} -H 'Custom-Header: test' https://httpbin.org/headers"
                        }
                    ]
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage examples: {str(e)}"
        )
