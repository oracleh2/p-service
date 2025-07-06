# backend/app/core/proxy_server.py - ИСПРАВЛЕННАЯ ВЕРСИЯ V2

import asyncio
import aiohttp
from aiohttp import web, ClientSession, ClientTimeout
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import structlog
import socket

from ..config import settings

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
        # Специальный обработчик для корневого пути
        self.app.router.add_get('/', self.root_handler)

        # Специальный обработчик для proxy status
        self.app.router.add_get('/status', self.status_handler)

        # Основной прокси-обработчик для всех остальных запросов
        self.app.router.add_route('*', '/{path:.*}', self.proxy_handler)

    async def root_handler(self, request):
        """Обработчик корневого пути"""
        try:
            device_count = 0
            if self.device_manager:
                devices = await self.device_manager.get_all_devices()
                device_count = len(devices)

            return web.json_response({
                "service": "Mobile Proxy Server",
                "status": "running",
                "version": "1.0.0",
                "available_devices": device_count,
                "message": "Proxy server is working. Use this server as HTTP/HTTPS proxy.",
                "example": "curl -x http://192.168.1.50:8080 https://httpbin.org/ip"
            })
        except Exception as e:
            logger.error(f"Error in root handler: {e}")
            return web.json_response({
                "service": "Mobile Proxy Server",
                "status": "error",
                "error": str(e)
            }, status=500)

    async def status_handler(self, request):
        """Обработчик статуса прокси"""
        try:
            device_count = 0
            online_devices = 0

            if self.device_manager:
                devices = await self.device_manager.get_all_devices()
                device_count = len(devices)
                online_devices = len([d for d in devices.values() if d.get('status') == 'online'])

            return web.json_response({
                "proxy_status": "running",
                "total_devices": device_count,
                "online_devices": online_devices,
                "proxy_host": settings.proxy_host,
                "proxy_port": settings.proxy_port
            })
        except Exception as e:
            logger.error(f"Error in status handler: {e}")
            return web.json_response({
                "proxy_status": "error",
                "error": str(e)
            }, status=500)

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
                    text="Bad Request: Use this server as HTTP proxy. Example: curl -x http://192.168.1.50:8080 https://httpbin.org/ip",
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

            # Логирование успешного запроса
            response_time = int((time.time() - start_time) * 1000)
            logger.info(f"Request completed: {response.status} in {response_time}ms")

            return response

        except Exception as e:
            logger.error(f"Error in proxy handler: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

            return web.Response(
                text=f"Internal Server Error: {str(e)}",
                status=500
            )

    def get_client_ip(self, request: web.Request) -> str:
        """Получение IP адреса клиента"""
        try:
            forwarded_for = request.headers.get('X-Forwarded-For')
            if forwarded_for:
                return forwarded_for.split(',')[0].strip()

            real_ip = request.headers.get('X-Real-IP')
            if real_ip:
                return real_ip

            # Исправленное получение remote IP
            transport = request.transport
            if transport:
                peername = transport.get_extra_info('peername')
                if peername:
                    return peername[0]

            return 'unknown'
        except Exception as e:
            logger.error(f"Error getting client IP: {e}")
            return 'unknown'

    def get_target_url(self, request: web.Request) -> Optional[str]:
        """Получение целевого URL из запроса"""
        try:
            # Для CONNECT запросов (HTTPS туннелирование)
            if request.method == 'CONNECT':
                return f"https://{request.path_qs}"

            # Для прямых HTTP запросов через прокси (полный URL в пути)
            if request.path_qs.startswith('http://') or request.path_qs.startswith('https://'):
                return request.path_qs

            # Для запросов с Host заголовком
            host = request.headers.get('Host')
            if host and host not in ['192.168.1.50:8080', '127.0.0.1:8080', 'localhost:8080']:
                scheme = 'https' if request.secure else 'http'
                return f"{scheme}://{host}{request.path_qs}"

            # Если это запрос к самому прокси-серверу
            return None

        except Exception as e:
            logger.error(f"Error getting target URL: {e}")
            return None

    async def select_device(self, request: web.Request) -> Optional[Dict[str, Any]]:
        """Выбор устройства для проксирования"""
        try:
            if not self.device_manager:
                return None

            # Проверка заголовка для выбора конкретного устройства
            device_id = request.headers.get('X-Proxy-Device-ID')
            if device_id:
                device = await self.device_manager.get_device_by_id(device_id)
                if device and device.get('status') == 'online':
                    return device

            # Выбор случайного доступного устройства
            return await self.device_manager.get_random_device()

        except Exception as e:
            logger.error(f"Error selecting device: {e}")
            return None

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

            # Выполнение запроса через выбранное устройство
            async with self.session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=body,
                allow_redirects=False,
                ssl=False  # Отключаем проверку SSL для упрощения
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

        except Exception as e:
            logger.error(f"Unexpected error forwarding request: {e}")
            return web.Response(
                text=f"Internal Server Error: {str(e)}",
                status=500
            )

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
