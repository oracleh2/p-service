# backend/app/core/proxy_server.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import asyncio
import aiohttp
from aiohttp import web, ClientSession, ClientTimeout
from aiohttp.web import Request, Response, StreamResponse
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import structlog
import socket

from ..config import settings
from ..models.database import AsyncSessionLocal
from ..models.base import RequestLog
from datetime import datetime, timezone
import uuid

logger = structlog.get_logger()


class ProxyServer:
    """HTTP прокси-сервер для маршрутизации запросов через мобильные устройства"""

    def __init__(self, device_manager, stats_collector):
        self.device_manager = device_manager
        self.stats_collector = stats_collector
        self.app = None
        self.runner = None
        self.site = None
        self.session: Optional[ClientSession] = None
        self.running = False

    async def start(self):
        """Запуск прокси-сервера"""
        try:
            logger.info(f"Starting proxy server on {settings.proxy_host}:{settings.proxy_port}")

            # Создание HTTP сессии
            self.session = ClientSession(
                timeout=ClientTimeout(total=settings.request_timeout_seconds),
                connector=aiohttp.TCPConnector(
                    limit=settings.max_concurrent_connections,
                    limit_per_host=50,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                )
            )

            # Создание веб-приложения
            self.app = web.Application()
            self.setup_routes()

            # Запуск сервера
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(
                self.runner,
                settings.proxy_host,
                settings.proxy_port
            )

            await self.site.start()
            self.running = True

            logger.info(
                f"✅ Proxy server started successfully on {settings.proxy_host}:{settings.proxy_port}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to start proxy server: {e}")
            self.running = False
            raise

    async def stop(self):
        """Остановка прокси-сервера"""
        self.running = False

        if self.site:
            await self.site.stop()

        if self.runner:
            await self.runner.cleanup()

        if self.session:
            await self.session.close()

        logger.info("Proxy server stopped")

    def is_running(self) -> bool:
        """Проверка состояния сервера"""
        return self.running

    def setup_routes(self):
        """Настройка маршрутов"""
        # Основной прокси-обработчик для всех запросов
        self.app.router.add_route('*', '/{path:.*}', self.proxy_handler)

        # Также добавим специальные обработчики
        self.app.router.add_get('/', self.root_handler)

    async def root_handler(self, request):
        """Обработчик корневого пути"""
        return web.json_response({
            "service": "Mobile Proxy Server",
            "status": "running",
            "version": "1.0.0",
            "available_devices": len(await self.device_manager.get_all_devices()) if self.device_manager else 0
        })

    async def proxy_handler(self, request: web.Request) -> web.Response:
        """Основной обработчик прокси-запросов"""
        start_time = time.time()
        client_ip = self.get_client_ip(request)

        try:
            logger.info(f"Proxy request: {request.method} {request.url} from {client_ip}")

            # Получение целевого URL
            target_url = self.get_target_url(request)
            if not target_url:
                logger.warning(f"Bad request: no target URL - {request.url}")
                return web.Response(
                    text="Bad Request: Invalid URL - use proxy with target URL",
                    status=400
                )

            logger.info(f"Target URL: {target_url}")

            # Выбор устройства для проксирования
            device = await self.select_device(request)
            if not device:
                logger.warning("No devices available for proxy")
                return web.Response(
                    text="Service Unavailable: No devices available",
                    status=503
                )

            logger.info(f"Selected device: {device['id']} ({device['type']})")

            # Выполнение запроса через устройство
            response = await self.forward_request(request, target_url, device)

            # Логирование и статистика
            response_time = int((time.time() - start_time) * 1000)
            logger.info(f"Request completed: {response.status} in {response_time}ms")

            await self.log_request(
                device_id=device['id'],
                client_ip=client_ip,
                target_url=target_url,
                method=request.method,
                status_code=response.status,
                response_time=response_time,
                user_agent=request.headers.get('User-Agent', ''),
                request_size=request.content_length or 0,
                response_size=len(response.body) if hasattr(response, 'body') else 0
            )

            return response

        except Exception as e:
            logger.error(f"Error in proxy handler: {e}")

            # Логирование ошибки
            response_time = int((time.time() - start_time) * 1000)
            await self.log_request(
                device_id=None,
                client_ip=client_ip,
                target_url=str(request.url),
                method=request.method,
                status_code=500,
                response_time=response_time,
                error_message=str(e),
                user_agent=request.headers.get('User-Agent', ''),
                request_size=request.content_length or 0
            )

            return web.Response(
                text=f"Internal Server Error: {str(e)}",
                status=500
            )

    def get_client_ip(self, request: web.Request) -> str:
        """Получение IP адреса клиента"""
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()

        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

        if hasattr(request, 'remote') and request.remote:
            return request.remote

        return 'unknown'

    def get_target_url(self, request: web.Request) -> Optional[str]:
        """Получение целевого URL из запроса"""
        # Для прямых HTTP запросов через прокси
        if request.path.startswith('http'):
            return request.path

        # Проверяем заголовки
        host = request.headers.get('Host')
        if host and not host.startswith('127.0.0.1') and not host.startswith('localhost') and not host.startswith(
            '192.168.1.50'):
            scheme = 'https' if request.secure else 'http'
            return f"{scheme}://{host}{request.path_qs}"

        # Для тестирования - если это запрос к нашему серверу, возвращаем тестовый URL
        if request.path == '/':
            return None

        # Возвращаем тестовый URL для отладки
        return "https://httpbin.org/ip"

    async def select_device(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """Выбор устройства для проксирования"""
        if not self.device_manager:
            return None

        # Проверка заголовка для выбора конкретного устройства
        device_id = request.headers.get('X-Proxy-Device-ID')
        if device_id:
            device = await self.device_manager.get_device_by_id(device_id)
            if device and device['status'] == 'online':
                return device

        # Выбор случайного доступного устройства
        return await self.device_manager.get_random_device()

    async def forward_request(
        self,
        request: web.Request,
        target_url: str,
        device: Dict[str, Any]
    ) -> web.Response:
        """Перенаправление запроса через устройство"""
        try:
            # Подготовка заголовков
            headers = dict(request.headers)

            # Удаление служебных заголовков
            headers.pop('Host', None)
            headers.pop('X-Proxy-Device-ID', None)

            # Добавление заголовков для идентификации
            headers['X-Forwarded-For'] = self.get_client_ip(request)
            headers['User-Agent'] = headers.get('User-Agent', 'Mobile-Proxy/1.0')

            # Получение тела запроса
            body = None
            if request.method in ['POST', 'PUT', 'PATCH']:
                body = await request.read()

            logger.info(f"Forwarding {request.method} {target_url} via device {device['id']}")

            # Простое выполнение запроса без использования устройства как прокси
            # (для начала делаем прямой запрос)
            async with self.session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=body,
                allow_redirects=False,
                ssl=False  # Отключаем проверку SSL
            ) as response:

                # Получение тела ответа
                response_body = await response.read()

                # Копирование заголовков ответа
                response_headers = dict(response.headers)

                # Удаление заголовков, которые могут конфликтовать
                response_headers.pop('Transfer-Encoding', None)
                response_headers.pop('Content-Encoding', None)

                return web.Response(
                    body=response_body,
                    status=response.status,
                    headers=response_headers
                )

        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {target_url}")
            return web.Response(
                text="Request Timeout",
                status=504
            )

        except aiohttp.ClientError as e:
            logger.error(f"Client error during request to {target_url}: {e}")
            return web.Response(
                text="Bad Gateway",
                status=502
            )

    async def log_request(
        self,
        device_id: Optional[str],
        client_ip: str,
        target_url: str,
        method: str,
        status_code: int,
        response_time: int,
        user_agent: str = '',
        request_size: int = 0,
        response_size: int = 0,
        error_message: str = ''
    ):
        """Логирование запроса в базу данных"""
        try:
            # Пока просто логируем в консоль
            logger.info(
                f"Request logged: {method} {target_url} -> {status_code} ({response_time}ms) "
                f"from {client_ip} via {device_id or 'direct'}"
            )

            # TODO: добавить запись в БД когда она будет готова

        except Exception as e:
            logger.error(f"Failed to log request: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики прокси-сервера"""
        try:
            if self.device_manager:
                device_summary = await self.device_manager.get_summary()
            else:
                device_summary = {"total_devices": 0, "online_devices": 0}

            return {
                "devices": device_summary,
                "server_info": {
                    "running": self.running,
                    "host": settings.proxy_host,
                    "port": settings.proxy_port,
                    "max_connections": settings.max_concurrent_connections,
                    "timeout": settings.request_timeout_seconds
                }
            }

        except Exception as e:
            logger.error(f"Error getting proxy stats: {e}")
            return {"error": str(e)}
