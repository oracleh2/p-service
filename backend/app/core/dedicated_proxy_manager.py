# backend/app/core/dedicated_proxy_manager.py

import asyncio
import socket
import subprocess
import os
from typing import Dict, Any, Optional, List, Set
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from .managers import get_modem_manager
from ..models.database import AsyncSessionLocal
from ..models.base import ProxyDevice
from .dedicated_proxy_server import DedicatedProxyServer

logger = structlog.get_logger()


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
        """Загрузка существующих прокси-настроек из базы данных с принудительной очисткой портов"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice).where(
                    ProxyDevice.proxy_enabled == True,
                    ProxyDevice.dedicated_port.is_not(None)
                )
                result = await db.execute(stmt)
                devices = result.scalars().all()

                logger.info(f"Found {len(devices)} devices with dedicated proxies in database")

                for device in devices:
                    logger.info(f"Loading proxy for device: {device.name} on port {device.dedicated_port}")
                    try:
                        port = device.dedicated_port

                        # Проверяем доступность порта
                        port_available = await self.is_port_available(port)

                        if not port_available:
                            logger.warning(f"Port {port} is not available, trying to force cleanup...")

                            # Попробуем принудительно освободить порт
                            freed = await self.force_free_port(port)

                            if not freed:
                                logger.error(f"❌ Could not free port {port}, skipping device {device.name}")
                                continue

                        # Создаем прокси с небольшой задержкой
                        await asyncio.sleep(0.5)  # Даем время на освобождение порта

                        await self.create_dedicated_proxy(
                            device_id=device.name,
                            port=port,
                            username=device.proxy_username,
                            password=device.proxy_password
                        )
                        logger.info(f"✅ Successfully loaded proxy for {device.name}")

                    except Exception as e:
                        logger.error(f"❌ Failed to load proxy for {device.name}: {e}")

        except Exception as e:
            logger.error("Error loading existing proxies", error=str(e))

    async def create_dedicated_proxy(self, device_id: str, port: Optional[int] = None,
                                     username: Optional[str] = None, password: Optional[str] = None):
        """Создание индивидуального прокси для устройства с улучшенной проверкой портов"""
        try:
            # Валидация порта
            if port is not None:
                if not (self.port_range_start <= port <= self.port_range_end):
                    raise ValueError(f"Port must be in range {self.port_range_start}-{self.port_range_end}")

                # Проверка уникальности порта
                if port in self.used_ports:
                    logger.warning(f"Port {port} already in used_ports set, removing...")
                    self.used_ports.discard(port)  # Убираем из памяти

                # Двойная проверка доступности
                if not await self.is_port_available(port):
                    logger.warning(f"Port {port} is not available, trying to free it...")
                    freed = await self.force_free_port(port)
                    if not freed:
                        raise ValueError(f"Port {port} is not available and cannot be freed")

            # Генерация параметров если не указаны
            if port is None:
                port = await self.allocate_port()

            if username is None:
                username = f"device_{device_id[:8]}"

            if password is None:
                import secrets
                password = secrets.token_urlsafe(16)

            # Финальная проверка порта перед созданием сервера
            if not await self.is_port_available(port):
                raise ValueError(f"Port {port} is not available for creating proxy server")

            # Создание прокси-сервера (теперь используем новый класс)
            proxy_server = DedicatedProxyServer(
                device_id=device_id,
                port=port,
                username=username,
                password=password,
                device_manager=self.device_manager,
                modem_manager=get_modem_manager()
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
        """Улучшенная проверка доступности порта"""
        try:
            # Проверяем через socket bind
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(('0.0.0.0', port))
                    logger.debug(f"Port {port} is available via socket bind")
                    return True
                except OSError as e:
                    logger.debug(f"Port {port} bind failed: {e}")

                    # Дополнительная проверка через netstat
                    try:
                        import subprocess
                        result = subprocess.run(
                            ['netstat', '-tuln'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if f":{port} " in result.stdout:
                            logger.debug(f"Port {port} is in use according to netstat")
                            return False
                        else:
                            logger.debug(f"Port {port} not found in netstat, may be available")
                            # Попробуем с SO_REUSEPORT
                            try:
                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                                    s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                                    s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                                    s2.bind(('0.0.0.0', port))
                                    logger.debug(f"Port {port} available with SO_REUSEPORT")
                                    return True
                            except OSError:
                                logger.debug(f"Port {port} still not available with SO_REUSEPORT")
                                return False
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        logger.debug(f"netstat check failed for port {port}")
                        return False

                    return False

        except Exception as e:
            logger.error(f"Error checking port {port} availability: {e}")
            return False

    async def force_free_port(self, port: int) -> bool:
        """Принудительное освобождение порта"""
        try:
            logger.info(f"🔧 Trying to force free port {port}")

            # Найдем процессы, использующие порт
            try:
                import subprocess

                # Используем lsof для поиска процессов
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    logger.info(f"Found processes using port {port}: {pids}")

                    for pid in pids:
                        if pid.strip():
                            try:
                                logger.info(f"Attempting to kill process {pid}")
                                subprocess.run(['kill', '-TERM', pid.strip()], timeout=5)
                                await asyncio.sleep(1)  # Даем время на graceful shutdown

                                # Проверяем, что процесс завершился
                                check_result = subprocess.run(
                                    ['kill', '-0', pid.strip()],
                                    capture_output=True,
                                    timeout=2
                                )

                                if check_result.returncode == 0:
                                    logger.warning(f"Process {pid} still running, force killing")
                                    subprocess.run(['kill', '-KILL', pid.strip()], timeout=5)

                            except subprocess.TimeoutExpired:
                                logger.warning(f"Timeout killing process {pid}")
                            except Exception as e:
                                logger.warning(f"Error killing process {pid}: {e}")

                # Ждем немного и проверяем снова
                await asyncio.sleep(2)
                return await self.is_port_available(port)

            except (subprocess.TimeoutExpired, FileNotFoundError):
                logger.warning(f"lsof not available or timeout, trying alternative method")

                # Альтернативный метод через netstat + grep
                try:
                    result = subprocess.run(
                        ['sh', '-c', f'netstat -tulpn | grep ":{port} " | awk \'{{print $7}}\' | cut -d/ -f1'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )

                    if result.stdout.strip():
                        pids = [pid.strip() for pid in result.stdout.strip().split('\n') if
                                pid.strip() and pid.strip() != '-']
                        for pid in pids:
                            try:
                                subprocess.run(['kill', '-TERM', pid], timeout=5)
                            except:
                                pass

                        await asyncio.sleep(2)
                        return await self.is_port_available(port)

                except Exception as e:
                    logger.warning(f"Alternative port cleanup method failed: {e}")

                return False

        except Exception as e:
            logger.error(f"Error in force_free_port for port {port}: {e}")
            return False

    async def save_proxy_config(self, device_id: str, port: int, username: str, password: str):
        """Сохранение конфигурации прокси в базу данных"""
        try:
            async with AsyncSessionLocal() as db:
                # Ищем устройство по name, а не пытаемся преобразовать device_id в UUID
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
                # Ищем устройство по name
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

    async def verify_proxy_server_running(self, device_id: str) -> bool:
        """Проверка, что dedicated proxy сервер запущен и отвечает"""
        try:
            proxy_server = self.proxy_servers.get(device_id)
            if not proxy_server or not proxy_server.is_running():
                logger.error(f"Proxy server for {device_id} not running")
                return False

            # Проверяем, что порт слушается
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                result = s.connect_ex(('192.168.1.50', proxy_server.port))
                if result != 0:
                    logger.error(f"Proxy server port {proxy_server.port} not listening")
                    return False

            logger.info(f"Proxy server for {device_id} is running on port {proxy_server.port}")
            return True

        except Exception as e:
            logger.error(f"Error verifying proxy server: {e}")
            return False
