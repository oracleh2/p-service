# backend/app/core/dedicated_proxy_manager.py

import asyncio
import base64
import aiohttp
from aiohttp import web, BasicAuth
from typing import Dict, Any, Optional, List, Set
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import socket
import uuid

from ..models.database import AsyncSessionLocal
from ..models.base import ProxyDevice
from ..utils.security import get_password_hash, verify_password

logger = structlog.get_logger()


class DedicatedProxyServer:
    """Индивидуальный прокси-сервер для конкретного устройства"""

    def __init__(self, device_id: str, port: int, username: str, password: str, device_manager):
        self.device_id = device_id
        self.port = port
        self.username = username
        self.password = password
        self.device_manager = device_manager
        self.app = None
        self.runner = None
        self.site = None
        self._running = False

    async def start(self):
        """Запуск индивидуального прокси-сервера"""
        if self._running:
            return

        try:
            # Создание веб-приложения
            self.app = web.Application()

            # Добавление middleware для аутентификации
            self.app.middlewares.append(self.auth_middleware)

            # Добавление роутов
            self.app.router.add_route('*', '/{path:.*}', self.proxy_handler)

            # Запуск сервера
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
            await self.site.start()

            self._running = True
            logger.info(
                "Dedicated proxy server started",
                device_id=self.device_id,
                port=self.port,
                username=self.username
            )

        except Exception as e:
            logger.error(
                "Failed to start dedicated proxy server",
                device_id=self.device_id,
                port=self.port,
                error=str(e)
            )
            raise

    async def stop(self):
        """Остановка индивидуального прокси-сервера"""
        if not self._running:
            return

        try:
            if self.site:
                await self.site.stop()
                self.site = None

            if self.runner:
                await self.runner.cleanup()
                self.runner = None

            self.app = None
            self._running = False

            logger.info(
                "Dedicated proxy server stopped",
                device_id=self.device_id,
                port=self.port
            )

        except Exception as e:
            logger.error(
                "Error stopping dedicated proxy server",
                device_id=self.device_id,
                port=self.port,
                error=str(e)
            )

    @web.middleware
    async def auth_middleware(self, request, handler):
        """Middleware для проверки аутентификации"""
        # Получение заголовка авторизации
        auth_header = request.headers.get('Proxy-Authorization')

        if not auth_header:
            return web.Response(
                status=407,
                headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
                text="Proxy Authentication Required"
            )

        try:
            # Парсинг Basic Auth
            if not auth_header.startswith('Basic '):
                raise ValueError("Invalid auth method")

            encoded_credentials = auth_header[6:]
            decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
            username, password = decoded_credentials.split(':', 1)

            # Проверка учетных данных
            if username != self.username or password != self.password:
                return web.Response(
                    status=407,
                    headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
                    text="Invalid credentials"
                )

        except Exception as e:
            return web.Response(
                status=407,
                headers={'Proxy-Authenticate': 'Basic realm="Proxy"'},
                text="Authentication error"
            )

        # Передача управления дальше
        return await handler(request)

    async def proxy_handler(self, request):
        """Обработчик прокси-запросов для конкретного устройства"""
        try:
            # Получение информации об устройстве
            device = await self.device_manager.get_device_by_id(self.device_id)
            if not device or device['status'] != 'online':
                return web.Response(
                    status=503,
                    text="Device not available"
                )

            # Подготовка целевого URL
            if request.method == 'CONNECT':
                # HTTPS туннелирование
                return await self.handle_connect(request, device)
            else:
                # HTTP прокси
                return await self.handle_http(request, device)

        except Exception as e:
            logger.error(
                "Error in dedicated proxy handler",
                device_id=self.device_id,
                error=str(e)
            )
            return web.Response(
                status=500,
                text="Internal proxy error"
            )

    async def handle_http(self, request, device):
        """Обработка HTTP запросов"""
        # Получение целевого URL из пути запроса
        target_url = str(request.url)

        # Подготовка заголовков
        headers = dict(request.headers)
        headers.pop('Proxy-Authorization', None)
        headers.pop('Host', None)

        # Выполнение запроса через устройство
        try:
            # Здесь должна быть логика прокси через конкретное устройство
            # Пока используем простую реализацию через aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=await request.read() if request.content_length else None
                ) as response:
                    # Подготовка ответа
                    body = await response.read()

                    return web.Response(
                        status=response.status,
                        headers=dict(response.headers),
                        body=body
                    )

        except Exception as e:
            logger.error(
                "Error proxying HTTP request",
                device_id=self.device_id,
                target_url=target_url,
                error=str(e)
            )
            return web.Response(
                status=502,
                text="Bad Gateway"
            )

    async def handle_connect(self, request, device):
        """Обработка CONNECT запросов (HTTPS туннелирование)"""
        # Упрощенная реализация CONNECT
        return web.Response(
            status=200,
            text="Connection established"
        )

    def is_running(self):
        """Проверка статуса работы сервера"""
        return self._running


class DedicatedProxyManager:
    """Менеджер индивидуальных прокси-серверов"""

    def __init__(self, device_manager):
        self.device_manager = device_manager
        self.proxy_servers: Dict[str, DedicatedProxyServer] = {}
        self.used_ports: Set[int] = set()
        self.port_range_start = 6001
        self.port_range_end = 7000
        self._running = False

    async def start(self):
        """Запуск менеджера индивидуальных прокси"""
        if self._running:
            return

        logger.info("Starting dedicated proxy manager")

        # Загрузка существующих устройств с настроенными прокси
        await self.load_existing_proxies()

        self._running = True
        logger.info("Dedicated proxy manager started")

    async def stop(self):
        """Остановка менеджера индивидуальных прокси"""
        if not self._running:
            return

        logger.info("Stopping dedicated proxy manager")

        # Остановка всех прокси-серверов
        for proxy_server in self.proxy_servers.values():
            await proxy_server.stop()

        self.proxy_servers.clear()
        self.used_ports.clear()
        self._running = False

        logger.info("Dedicated proxy manager stopped")

    async def load_existing_proxies(self):
        """Загрузка существующих прокси-настроек из базы данных"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice).where(
                    ProxyDevice.proxy_enabled == True,
                    ProxyDevice.dedicated_port.is_not(None)
                )
                result = await db.execute(stmt)
                devices = result.scalars().all()

                for device in devices:
                    await self.create_dedicated_proxy(
                        device_id=str(device.id),
                        port=device.dedicated_port,
                        username=device.proxy_username,
                        password=device.proxy_password
                    )

        except Exception as e:
            logger.error("Error loading existing proxies", error=str(e))

    async def create_dedicated_proxy(self, device_id: str, port: Optional[int] = None,
                                     username: Optional[str] = None, password: Optional[str] = None):
        """Создание индивидуального прокси для устройства"""
        try:
            # Валидация порта
            if port is not None:
                if not (self.port_range_start <= port <= self.port_range_end):
                    raise ValueError(f"Port must be in range {self.port_range_start}-{self.port_range_end}")

                # Проверка уникальности порта
                if port in self.used_ports or not await self.is_port_available(port):
                    raise ValueError(f"Port {port} is already in use")

            # Генерация параметров если не указаны
            if port is None:
                port = await self.allocate_port()

            if username is None:
                username = f"device_{device_id[:8]}"

            if password is None:
                import secrets
                password = secrets.token_urlsafe(16)

            # Проверка доступности порта (повторная проверка для автоматически выделенного)
            if port in self.used_ports or not await self.is_port_available(port):
                raise ValueError(f"Port {port} is not available")

            # Создание прокси-сервера
            proxy_server = DedicatedProxyServer(
                device_id=device_id,
                port=port,
                username=username,
                password=password,
                device_manager=self.device_manager
            )

            # Запуск сервера
            await proxy_server.start()

            # Сохранение в памяти и базе данных
            self.proxy_servers[device_id] = proxy_server
            self.used_ports.add(port)

            await self.save_proxy_config(device_id, port, username, password)

            logger.info(
                "Dedicated proxy created",
                device_id=device_id,
                port=port,
                username=username
            )

            return {
                "device_id": device_id,
                "port": port,
                "username": username,
                "password": password,
                "proxy_url": f"http://192.168.1.50:{port}",
                "status": "running"
            }

        except Exception as e:
            logger.error(
                "Error creating dedicated proxy",
                device_id=device_id,
                error=str(e)
            )
            raise

    async def remove_dedicated_proxy(self, device_id: str):
        """Удаление индивидуального прокси для устройства"""
        try:
            proxy_server = self.proxy_servers.get(device_id)
            if proxy_server:
                port = proxy_server.port
                await proxy_server.stop()

                del self.proxy_servers[device_id]
                self.used_ports.discard(port)

                # Удаление из базы данных
                await self.remove_proxy_config(device_id)

                logger.info(
                    "Dedicated proxy removed",
                    device_id=device_id,
                    port=port
                )

        except Exception as e:
            logger.error(
                "Error removing dedicated proxy",
                device_id=device_id,
                error=str(e)
            )
            raise

    async def get_device_proxy_info(self, device_id: str):
        """Получение информации о прокси устройства"""
        proxy_server = self.proxy_servers.get(device_id)
        if not proxy_server:
            return None

        return {
            "device_id": device_id,
            "port": proxy_server.port,
            "username": proxy_server.username,
            "password": proxy_server.password,
            "proxy_url": f"http://192.168.1.50:{proxy_server.port}",
            "status": "running" if proxy_server.is_running() else "stopped"
        }

    async def list_all_dedicated_proxies(self):
        """Список всех индивидуальных прокси"""
        proxies = []
        for device_id, proxy_server in self.proxy_servers.items():
            proxy_info = await self.get_device_proxy_info(device_id)
            if proxy_info:
                proxies.append(proxy_info)
        return proxies

    async def allocate_port(self) -> int:
        """Выделение свободного порта"""
        for port in range(self.port_range_start, self.port_range_end + 1):
            if port not in self.used_ports and await self.is_port_available(port):
                return port
        raise RuntimeError("No available ports in range")

    async def is_port_available(self, port: int) -> bool:
        """Проверка доступности порта"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return True
        except OSError:
            return False

    async def save_proxy_config(self, device_id: str, port: int, username: str, password: str):
        """Сохранение конфигурации прокси в базу данных"""
        try:
            async with AsyncSessionLocal() as db:
                # ИСПРАВЛЕНИЕ: Ищем устройство по name, а не пытаемся преобразовать device_id в UUID
                stmt = select(ProxyDevice).where(ProxyDevice.name == device_id)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()

                if not device:
                    raise ValueError(f"Device with name {device_id} not found in database")

                # Используем реальный UUID устройства
                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == device.id  # Используем найденный UUID
                ).values(
                    dedicated_port=port,
                    proxy_username=username,
                    proxy_password=password,
                    proxy_enabled=True
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error(
                "Error saving proxy config",
                device_id=device_id,
                error=str(e)
            )
            raise

    async def remove_proxy_config(self, device_id: str):
        """Удаление конфигурации прокси из базы данных"""
        try:
            async with AsyncSessionLocal() as db:
                # ИСПРАВЛЕНИЕ: Ищем устройство по name
                stmt = select(ProxyDevice).where(ProxyDevice.name == device_id)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()

                if not device:
                    raise ValueError(f"Device with name {device_id} not found in database")

                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == device.id  # Используем найденный UUID
                ).values(
                    dedicated_port=None,
                    proxy_username=None,
                    proxy_password=None,
                    proxy_enabled=False
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error(
                "Error removing proxy config",
                device_id=device_id,
                error=str(e)
            )
            raise
