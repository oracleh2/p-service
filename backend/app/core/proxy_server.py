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
from ..database import AsyncSessionLocal
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
            # Создание HTTP сессии
            self.session = ClientSession(
                timeout=ClientTimeout(total=settings.REQUEST_TIMEOUT_SECONDS),
                connector=aiohttp.TCPConnector(
                    limit=settings.MAX_CONCURRENT_CONNECTIONS,
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
                settings.PROXY_HOST,
                settings.PROXY_PORT
            )

            await self.site.start()
            self.running = True

            logger.info(
                "Proxy server started",
                host=settings.PROXY_HOST,
                port=settings.PROXY_PORT
            )

        except Exception as e:
            logger.error("Failed to start proxy server", error=str(e))
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
        # Основной прокси-обработчик
        self.app.router.add_route('*', '/{path:.*}', self.proxy_handler)

        # Служебные эндпоинты
        self.app.router.add_get('/proxy/health', self.health_handler)
        self.app.router.add_get('/proxy/status', self.status_handler)

    async def proxy_handler(self, request: Request) -> Response:
        """Основной обработчик прокси-запросов"""
        start_time = time.time()
        client_ip = self.get_client_ip(request)

        try:
            # Получение целевого URL
            target_url = self.get_target_url(request)
            if not target_url:
                return web.Response(
                    text="Bad Request: Invalid URL",
                    status=400
                )

            # Выбор устройства для проксирования
            device = await self.select_device(request)
            if not device:
                return web.Response(
                    text="Service Unavailable: No devices available",
                    status=503
                )

            # Выполнение запроса через устройство
            response = await self.forward_request(request, target_url, device)

            # Логирование и статистика
            response_time = int((time.time() - start_time) * 1000)
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

            # Обновление статистики устройства
            await self.device_manager.update_device_stats(
                device['id'],
                response_time,
                200 <= response.status < 400
            )

            return response

        except Exception as e:
            logger.error(
                "Error in proxy handler",
                error=str(e),
                client_ip=client_ip,
                method=request.method,
                url=str(request.url)
            )

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
                text="Internal Server Error",
                status=500
            )

    def get_client_ip(self, request: Request) -> str:
        """Получение IP адреса клиента"""
        # Проверка заголовков прокси
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()

        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

        # Fallback на remote IP
        if request.remote:
            return request.remote

        return 'unknown'

    def get_target_url(self, request: Request) -> Optional[str]:
        """Получение целевого URL из запроса"""
        # Для CONNECT метода (HTTPS туннелирование)
        if request.method == 'CONNECT':
            return f"https://{request.path}"

        # Для обычных HTTP запросов
        if request.path.startswith('http'):
            return request.path

        # Попытка получить URL из заголовков
        host = request.headers.get('Host')
        if host:
            scheme = 'https' if request.secure else 'http'
            return f"{scheme}://{host}{request.path_qs}"

        return None

    async def select_device(self, request: Request) -> Optional[Dict[str, Any]]:
        """Выбор устройства для проксирования"""
        # Можно добавить различные стратегии выбора устройства
        # Например, по заголовкам, по IP клиента, по оператору и т.д.

        # Проверка заголовка для выбора по оператору
        preferred_operator = request.headers.get('X-Proxy-Operator')
        if preferred_operator:
            device = await self.device_manager.get_device_by_operator(preferred_operator)
            if device:
                return device

        # Проверка заголовка для выбора по региону
        preferred_region = request.headers.get('X-Proxy-Region')
        if preferred_region:
            device = await self.device_manager.get_device_by_region(preferred_region)
            if device:
                return device

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
            request: Request,
            target_url: str,
            device: Dict[str, Any]
    ) -> Response:
        """Перенаправление запроса через устройство"""
        # Подготовка заголовков
        headers = dict(request.headers)

        # Удаление служебных заголовков
        headers.pop('Host', None)
        headers.pop('X-Proxy-Operator', None)
        headers.pop('X-Proxy-Region', None)
        headers.pop('X-Proxy-Device-ID', None)

        # Добавление заголовков для идентификации
        headers['X-Forwarded-For'] = self.get_client_ip(request)
        headers['X-Forwarded-Proto'] = 'https' if request.secure else 'http'

        # Прокси через устройство
        device_proxy = f"http://{device['ip_address']}:{device['port']}"

        try:
            # Получение тела запроса
            body = None
            if request.method in ['POST', 'PUT', 'PATCH']:
                body = await request.read()

            # Выполнение запроса
            async with self.session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=body,
                    proxy=device_proxy,
                    allow_redirects=False,
                    ssl=False  # Отключаем проверку SSL для прокси
            ) as response:

                # Подготовка ответа
                body = await response.read()

                # Копирование заголовков ответа
                response_headers = dict(response.headers)

                # Удаление заголовков, которые могут конфликтовать
                response_headers.pop('Transfer-Encoding', None)
                response_headers.pop('Content-Encoding', None)

                return web.Response(
                    body=body,
                    status=response.status,
                    headers=response_headers
                )

        except asyncio.TimeoutError:
            logger.error(
                "Request timeout",
                target_url=target_url,
                device_id=device['id']
            )
            return web.Response(
                text="Request Timeout",
                status=504
            )

        except aiohttp.ClientError as e:
            logger.error(
                "Client error during request",
                target_url=target_url,
                device_id=device['id'],
                error=str(e)
            )
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
            async with AsyncSessionLocal() as db:
                log_entry = RequestLog(
                    device_id=uuid.UUID(device_id) if device_id else None,
                    client_ip=client_ip,
                    target_url=target_url,
                    method=method,
                    status_code=status_code,
                    response_time_ms=response_time,
                    user_agent=user_agent,
                    request_size=request_size,
                    response_size=response_size,
                    error_message=error_message if error_message else None
                )

                db.add(log_entry)
                await db.commit()

        except Exception as e:
            logger.error("Failed to log request", error=str(e))

    async def health_handler(self, request: Request) -> Response:
        """Обработчик проверки здоровья прокси"""
        try:
            available_devices = await self.device_manager.get_available_devices()

            health_data = {
                "status": "healthy",
                "proxy_server": "running",
                "available_devices": len(available_devices),
                "total_devices": len(self.device_manager.devices),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            return web.json_response(health_data)

        except Exception as e:
            logger.error("Error in health check", error=str(e))
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500
            )

    async def status_handler(self, request: Request) -> Response:
        """Обработчик статуса прокси"""
        try:
            device_summary = await self.device_manager.get_summary()

            status_data = {
                "proxy_server": {
                    "running": self.running,
                    "host": settings.PROXY_HOST,
                    "port": settings.PROXY_PORT,
                    "max_connections": settings.MAX_CONCURRENT_CONNECTIONS,
                    "timeout": settings.REQUEST_TIMEOUT_SECONDS
                },
                "devices": device_summary,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            return web.json_response(status_data)

        except Exception as e:
            logger.error("Error getting proxy status", error=str(e))
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500
            )

    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики прокси-сервера"""
        try:
            device_summary = await self.device_manager.get_summary()

            # Здесь можно добавить дополнительную статистику
            # например, количество запросов в секунду, ошибок и т.д.

            return {
                "devices": device_summary,
                "server_info": {
                    "running": self.running,
                    "host": settings.PROXY_HOST,
                    "port": settings.PROXY_PORT,
                    "max_connections": settings.MAX_CONCURRENT_CONNECTIONS,
                    "timeout": settings.REQUEST_TIMEOUT_SECONDS
                }
            }

        except Exception as e:
            logger.error("Error getting proxy stats", error=str(e))
            return {"error": str(e)}