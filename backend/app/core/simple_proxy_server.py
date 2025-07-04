import asyncio
import aiohttp
from aiohttp import web, ClientSession, ClientTimeout
import time
from typing import Optional, Dict, Any
import structlog
import random
import requests

from ..config import settings
from ..database import AsyncSessionLocal
from ..models.base import RequestLog
from datetime import datetime, timezone
import uuid

logger = structlog.get_logger()


class SimpleProxyServer:
    """Упрощенный HTTP прокси-сервер для работы с модемами напрямую"""

    def __init__(self, modem_manager):
        self.modem_manager = modem_manager
        self.app = None
        self.runner = None
        self.site = None
        self.session: Optional[ClientSession] = None
        self.running = False
        self.proxy_routes = {}  # Маршруты для каждого модема

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

            # Настройка маршрутов для модемов
            await self.setup_modem_routes()

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
                "Simple proxy server started",
                host=settings.PROXY_HOST,
                port=settings.PROXY_PORT,
                modems_count=len(self.proxy_routes)
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

        logger.info("Simple proxy server stopped")

    def is_running(self) -> bool:
        """Проверка состояния сервера"""
        return self.running

    async def setup_modem_routes(self):
        """Настройка маршрутов для модемов"""
        try:
            modems = await self.modem_manager.get_all_modems()

            for modem_id, modem_info in modems.items():
                # Определение способа подключения к интернету через модем
                if modem_info['type'] == 'usb_modem':
                    # USB модем создает PPP интерфейс
                    route = await self.get_ppp_route(modem_id)
                elif modem_info['type'] == 'android':
                    # Android через USB tethering или WiFi hotspot
                    route = await self.get_android_route(modem_id)
                elif modem_info['type'] == 'network_modem':
                    # Сетевой модем
                    route = await self.get_network_route(modem_id)
                else:
                    continue

                if route:
                    self.proxy_routes[modem_id] = route
                    logger.info(
                        "Setup route for modem",
                        modem_id=modem_id,
                        route_type=route['type'],
                        interface=route.get('interface', 'N/A')
                    )

        except Exception as e:
            logger.error("Error setting up modem routes", error=str(e))

    async def get_ppp_route(self, modem_id: str) -> Optional[dict]:
        """Получение маршрута для PPP соединения"""
        try:
            # PPP интерфейс обычно создается автоматически
            # Нужно найти активный PPP интерфейс
            import netifaces

            for interface in netifaces.interfaces():
                if interface.startswith('ppp'):
                    return {
                        'type': 'ppp',
                        'interface': interface,
                        'method': 'interface_binding'
                    }

        except Exception as e:
            logger.error("Error getting PPP route", modem_id=modem_id, error=str(e))

        return None

    async def get_android_route(self, modem_id: str) -> Optional[dict]:
        """Получение маршрута для Android устройства"""
        try:
            # Android может создать USB tethering интерфейс
            # Обычно это usb0, rndis0 или похожие
            import netifaces

            android_interfaces = ['usb0', 'rndis0', 'enp0s20u1']

            for interface in android_interfaces:
                if interface in netifaces.interfaces():
                    return {
                        'type': 'android_tethering',
                        'interface': interface,
                        'method': 'interface_binding'
                    }

            # Если USB tethering не найден, можно попробовать WiFi hotspot
            # Но это сложнее, так как нужно знать IP Android устройства

        except Exception as e:
            logger.error("Error getting Android route", modem_id=modem_id, error=str(e))

        return None

    async def get_network_route(self, modem_id: str) -> Optional[dict]:
        """Получение маршрута для сетевого модема"""
        try:
            modem_info = await self.modem_manager.get_modem_status(modem_id)
            interface = modem_info.get('interface')

            if interface:
                return {
                    'type': 'network_interface',
                    'interface': interface,
                    'method': 'interface_binding'
                }

        except Exception as e:
            logger.error("Error getting network route", modem_id=modem_id, error=str(e))

        return None

    def setup_routes(self):
        """Настройка маршрутов веб-приложения"""
        # Основной прокси-обработчик
        self.app.router.add_route('*', '/{path:.*}', self.proxy_handler)

        # Служебные эндпоинты
        self.app.router.add_get('/proxy/health', self.health_handler)
        self.app.router.add_get('/proxy/status', self.status_handler)
        self.app.router.add_get('/proxy/modems', self.modems_handler)

    async def proxy_handler(self, request: web.Request) -> web.Response:
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

            # Выбор модема для проксирования
            modem_id = await self.select_modem(request)
            if not modem_id:
                return web.Response(
                    text="Service Unavailable: No modems available",
                    status=503
                )

            # Выполнение запроса через модем
            response = await self.forward_request_through_modem(
                request, target_url, modem_id
            )

            # Логирование
            response_time = int((time.time() - start_time) * 1000)
            await self.log_request(
                modem_id=modem_id,
                client_ip=client_ip,
                target_url=target_url,
                method=request.method,
                status_code=response.status,
                response_time=response_time,
                user_agent=request.headers.get('User-Agent', ''),
                request_size=request.content_length or 0
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

            return web.Response(
                text="Internal Server Error",
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

        if request.remote:
            return request.remote

        return 'unknown'

    def get_target_url(self, request: web.Request) -> Optional[str]:
        """Получение целевого URL из запроса"""
        if request.method == 'CONNECT':
            return f"https://{request.path}"

        if request.path.startswith('http'):
            return request.path

        host = request.headers.get('Host')
        if host:
            scheme = 'https' if request.secure else 'http'
            return f"{scheme}://{host}{request.path_qs}"

        return None

    async def select_modem(self, request: web.Request) -> Optional[str]:
        """Выбор модема для проксирования"""
        # Проверка заголовка для выбора конкретного модема
        modem_id = request.headers.get('X-Proxy-Modem-ID')
        if modem_id and modem_id in self.proxy_routes:
            online = await self.modem_manager.is_modem_online(modem_id)
            if online:
                return modem_id

        # Выбор случайного доступного модема
        available_modems = []
        for modem_id in self.proxy_routes.keys():
            if await self.modem_manager.is_modem_online(modem_id):
                available_modems.append(modem_id)

        if available_modems:
            return random.choice(available_modems)

        return None

    async def forward_request_through_modem(
            self,
            request: web.Request,
            target_url: str,
            modem_id: str
    ) -> web.Response:
        """Перенаправление запроса через модем"""
        try:
            # Получение маршрута для модема
            route = self.proxy_routes.get(modem_id)
            if not route:
                return web.Response(
                    text="Modem route not found",
                    status=502
                )

            # Подготовка заголовков
            headers = dict(request.headers)
            headers.pop('Host', None)
            headers.pop('X-Proxy-Modem-ID', None)
            headers['X-Forwarded-For'] = self.get_client_ip(request)

            # Получение тела запроса
            body = None
            if request.method in ['POST', 'PUT', 'PATCH']:
                body = await request.read()

            # Выполнение запроса через определенный сетевой интерфейс
            response = await self.make_request_through_interface(
                method=request.method,
                url=target_url,
                headers=headers,
                body=body,
                interface=route.get('interface'),
                route_type=route['type']
            )

            return response

        except Exception as e:
            logger.error(
                "Error forwarding request through modem",
                modem_id=modem_id,
                error=str(e)
            )
            return web.Response(
                text="Bad Gateway",
                status=502
            )

    async def make_request_through_interface(
            self,
            method: str,
            url: str,
            headers: dict,
            body: bytes,
            interface: str,
            route_type: str
    ) -> web.Response:
        """Выполнение запроса через определенный сетевой интерфейс"""
        try:
            # Для простоты используем requests с curl
            # В продакшене лучше использовать более сложную логику

            if route_type == 'ppp':
                # Для PPP соединения можно использовать curl с привязкой к интерфейсу
                response = await self.curl_request_with_interface(
                    method, url, headers, body, interface
                )
            elif route_type == 'android_tethering':
                # Для Android tethering тоже можно использовать curl
                response = await self.curl_request_with_interface(
                    method, url, headers, body, interface
                )
            else:
                # Обычный HTTP запрос
                response = await self.standard_http_request(
                    method, url, headers, body
                )

            return response

        except Exception as e:
            logger.error(
                "Error making request through interface",
                interface=interface,
                error=str(e)
            )
            return web.Response(
                text="Request failed",
                status=502
            )

    async def curl_request_with_interface(
            self,
            method: str,
            url: str,
            headers: dict,
            body: bytes,
            interface: str
    ) -> web.Response:
        """Выполнение запроса через curl с привязкой к интерфейсу"""
        try:
            # Построение команды curl
            cmd = [
                'curl',
                '-X', method,
                '--interface', interface,
                '--max-time', str(settings.REQUEST_TIMEOUT_SECONDS),
                '--silent',
                '--show-error',
                '--write-out', 'HTTPSTATUS:%{http_code}',
                url
            ]

            # Добавление заголовков
            for key, value in headers.items():
                cmd.extend(['-H', f'{key}: {value}'])

            # Добавление тела запроса
            if body:
                cmd.extend(['--data-binary', '@-'])

            # Выполнение команды
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if body else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate(input=body)

            if process.returncode != 0:
                logger.error(
                    "Curl request failed",
                    returncode=process.returncode,
                    stderr=stderr.decode()
                )
                return web.Response(
                    text="Request failed",
                    status=502
                )

            # Парсинг ответа
            output = stdout.decode()
            if 'HTTPSTATUS:' in output:
                parts = output.split('HTTPSTATUS:')
                response_body = parts[0]
                status_code = int(parts[1])
            else:
                response_body = output
                status_code = 200

            return web.Response(
                text=response_body,
                status=status_code
            )

        except Exception as e:
            logger.error(
                "Error in curl request",
                interface=interface,
                error=str(e)
            )
            return web.Response(
                text="Request failed",
                status=502
            )

    async def standard_http_request(
            self,
            method: str,
            url: str,
            headers: dict,
            body: bytes
    ) -> web.Response:
        """Обычный HTTP запрос"""
        try:
            async with self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=body,
                    allow_redirects=False
            ) as response:

                response_body = await response.read()
                response_headers = dict(response.headers)

                # Удаление конфликтующих заголовков
                response_headers.pop('Transfer-Encoding', None)
                response_headers.pop('Content-Encoding', None)

                return web.Response(
                    body=response_body,
                    status=response.status,
                    headers=response_headers
                )

        except Exception as e:
            logger.error(
                "Error in standard HTTP request",
                error=str(e)
            )
            return web.Response(
                text="Request failed",
                status=502
            )

    async def log_request(
            self,
            modem_id: str,
            client_ip: str,
            target_url: str,
            method: str,
            status_code: int,
            response_time: int,
            user_agent: str = '',
            request_size: int = 0,
            error_message: str = ''
    ):
        """Логирование запроса"""
        try:
            async with AsyncSessionLocal() as db:
                log_entry = RequestLog(
                    device_id=uuid.UUID(modem_id) if modem_id else None,
                    client_ip=client_ip,
                    target_url=target_url,
                    method=method,
                    status_code=status_code,
                    response_time_ms=response_time,
                    user_agent=user_agent,
                    request_size=request_size,
                    error_message=error_message if error_message else None
                )

                db.add(log_entry)
                await db.commit()

        except Exception as e:
            logger.error("Failed to log request", error=str(e))

    async def health_handler(self, request: web.Request) -> web.Response:
        """Обработчик проверки здоровья"""
        try:
            modems = await self.modem_manager.get_all_modems()
            online_modems = 0

            for modem_id in modems.keys():
                if await self.modem_manager.is_modem_online(modem_id):
                    online_modems += 1

            health_data = {
                "status": "healthy",
                "proxy_server": "running",
                "total_modems": len(modems),
                "online_modems": online_modems,
                "routes_configured": len(self.proxy_routes),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            return web.json_response(health_data)

        except Exception as e:
            logger.error("Error in health check", error=str(e))
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500
            )

    async def status_handler(self, request: web.Request) -> web.Response:
        """Обработчик статуса прокси"""
        try:
            modems = await self.modem_manager.get_all_modems()
            modem_statuses = {}

            for modem_id in modems.keys():
                modem_statuses[modem_id] = {
                    "online": await self.modem_manager.is_modem_online(modem_id),
                    "external_ip": await self.modem_manager.get_modem_external_ip(modem_id),
                    "route_configured": modem_id in self.proxy_routes
                }

            status_data = {
                "proxy_server": {
                    "running": self.running,
                    "host": settings.PROXY_HOST,
                    "port": settings.PROXY_PORT,
                },
                "modems": modem_statuses,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            return web.json_response(status_data)

        except Exception as e:
            logger.error("Error getting proxy status", error=str(e))
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500
            )

    async def modems_handler(self, request: web.Request) -> web.Response:
        """Обработчик списка модемов"""
        try:
            modems = await self.modem_manager.get_all_modems()
            modems_info = []

            for modem_id, modem_info in modems.items():
                status = await self.modem_manager.get_modem_status(modem_id)
                modems_info.append({
                    "id": modem_id,
                    "type": modem_info['type'],
                    "interface": modem_info['interface'],
                    "online": await self.modem_manager.is_modem_online(modem_id),
                    "external_ip": status.get('external_ip'),
                    "details": status
                })

            return web.json_response({
                "modems": modems_info,
                "total": len(modems_info),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

        except Exception as e:
            logger.error("Error getting modems info", error=str(e))
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500
            )