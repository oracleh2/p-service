import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import uuid

from ..database import AsyncSessionLocal, get_system_config
from ..models.base import ProxyDevice, RotationConfig
from ..config import settings

logger = structlog.get_logger()


class RotationManager:
    """Менеджер автоматической ротации IP адресов"""

    def __init__(self, modem_manager):
        self.modem_manager = modem_manager
        self.rotation_tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        self.rotation_in_progress: Dict[str, bool] = {}

    async def start(self):
        """Запуск менеджера ротации"""
        self.running = True

        # Запуск задач ротации для всех модемов
        await self.start_rotation_tasks()

        logger.info("Rotation manager started")

    async def stop(self):
        """Остановка менеджера ротации"""
        self.running = False

        # Остановка всех задач ротации
        for task in self.rotation_tasks.values():
            task.cancel()

        # Ожидание завершения задач
        if self.rotation_tasks:
            await asyncio.gather(*self.rotation_tasks.values(), return_exceptions=True)

        self.rotation_tasks.clear()

        logger.info("Rotation manager stopped")

    async def start_rotation_tasks(self):
        """Запуск задач ротации для всех модемов"""
        try:
            async with AsyncSessionLocal() as db:
                # Получение всех модемов с конфигурацией ротации
                stmt = select(ProxyDevice, RotationConfig).join(
                    RotationConfig, ProxyDevice.id == RotationConfig.device_id
                ).where(
                    ProxyDevice.status.in_(['online', 'offline']),
                    RotationConfig.auto_rotation == True
                )

                result = await db.execute(stmt)
                devices_with_config = result.all()

                for device, config in devices_with_config:
                    device_id = str(device.id)

                    # Создание задачи ротации для устройства
                    task = asyncio.create_task(
                        self.modem_rotation_loop(device_id, config.rotation_interval)
                    )
                    self.rotation_tasks[device_id] = task

                    logger.info(
                        "Started rotation task for modem",
                        modem_id=device_id,
                        interval=config.rotation_interval
                    )

        except Exception as e:
            logger.error("Failed to start rotation tasks", error=str(e))

    async def modem_rotation_loop(self, modem_id: str, interval: int):
        """Цикл автоматической ротации для модема"""
        while self.running:
            try:
                # Ожидание интервала ротации
                await asyncio.sleep(interval)

                if not self.running:
                    break

                # Проверка, не происходит ли уже ротация
                if self.rotation_in_progress.get(modem_id, False):
                    logger.debug("Rotation already in progress", modem_id=modem_id)
                    continue

                # Проверка, что модем онлайн
                if not await self.modem_manager.is_modem_online(modem_id):
                    logger.debug("Modem not online, skipping rotation", modem_id=modem_id)
                    continue

                # Проверка глобальной настройки автоматической ротации
                auto_rotation_enabled = await get_system_config('auto_rotation_enabled', True)
                if not auto_rotation_enabled:
                    logger.debug("Auto rotation disabled globally")
                    continue

                # Выполнение ротации
                await self.rotate_modem_ip(modem_id)

            except asyncio.CancelledError:
                logger.info("Rotation loop cancelled", modem_id=modem_id)
                break
            except Exception as e:
                logger.error(
                    "Errorimport asyncio
                import aiohttp
                from datetime import datetime, timezone, timedelta
                from typing import Dict, Optional, List
                from sqlalchemy import select, update
                from sqlalchemy.ext.asyncio import AsyncSession
                import structlog
                import uuid

                from ..database import AsyncSessionLocal, get_system_config
                from ..models.base import ProxyDevice, RotationConfig
                from ..config import settings

                logger = structlog.get_logger()


class RotationManager:
    """Менеджер автоматической ротации IP адресов"""

    def __init__(self, device_manager):
        self.device_manager = device_manager
        self.rotation_tasks: Dict[str, asyncio.Task] = {}
        self.running = False
        self.session: Optional[aiohttp.ClientSession] = None
        self.rotation_in_progress: Dict[str, bool] = {}

    async def start(self):
        """Запуск менеджера ротации"""
        self.running = True
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            connector=aiohttp.TCPConnector(limit=50)
        )

        # Запуск задач ротации для всех устройств
        await self.start_rotation_tasks()

        logger.info("Rotation manager started")

    async def stop(self):
        """Остановка менеджера ротации"""
        self.running = False

        # Остановка всех задач ротации
        for task in self.rotation_tasks.values():
            task.cancel()

        # Ожидание завершения задач
        if self.rotation_tasks:
            await asyncio.gather(*self.rotation_tasks.values(), return_exceptions=True)

        self.rotation_tasks.clear()

        if self.session:
            await self.session.close()

        logger.info("Rotation manager stopped")

    async def start_rotation_tasks(self):
        """Запуск задач ротации для всех устройств"""
        try:
            async with AsyncSessionLocal() as db:
                # Получение всех устройств с конфигурацией ротации
                stmt = select(ProxyDevice, RotationConfig).join(
                    RotationConfig, ProxyDevice.id == RotationConfig.device_id
                ).where(
                    ProxyDevice.status.in_(['online', 'offline']),
                    RotationConfig.auto_rotation == True
                )

                result = await db.execute(stmt)
                devices_with_config = result.all()

                for device, config in devices_with_config:
                    device_id = str(device.id)

                    # Создание задачи ротации для устройства
                    task = asyncio.create_task(
                        self.device_rotation_loop(device_id, config.rotation_interval)
                    )
                    self.rotation_tasks[device_id] = task

                    logger.info(
                        "Started rotation task for device",
                        device_id=device_id,
                        device_name=device.name,
                        interval=config.rotation_interval
                    )

        except Exception as e:
            logger.error("Failed to start rotation tasks", error=str(e))

    async def device_rotation_loop(self, device_id: str, interval: int):
        """Цикл автоматической ротации для устройства"""
        while self.running:
            try:
                # Ожидание интервала ротации
                await asyncio.sleep(interval)

                if not self.running:
                    break

                # Проверка, не происходит ли уже ротация
                if self.rotation_in_progress.get(device_id, False):
                    logger.debug("Rotation already in progress", device_id=device_id)
                    continue

                # Проверка, что устройство онлайн
                device = await self.device_manager.get_device_by_id(device_id)
                if not device or device['status'] != 'online':
                    logger.debug("Device not online, skipping rotation", device_id=device_id)
                    continue

                # Проверка глобальной настройки автоматической ротации
                auto_rotation_enabled = await get_system_config('auto_rotation_enabled', True)
                if not auto_rotation_enabled:
                    logger.debug("Auto rotation disabled globally")
                    continue

                # Выполнение ротации
                await self.rotate_device_ip(device_id)

            except asyncio.CancelledError:
                logger.info("Rotation loop cancelled", device_id=device_id)
                break
            except Exception as e:
                logger.error(
                    "Error in rotation loop",
                    device_id=device_id,
                    error=str(e)
                )
                # Пауза перед повторной попыткой
                await asyncio.sleep(60)

    async def rotate_device_ip(self, device_id: str) -> bool:
        """Ротация IP адреса устройства"""
        try:
            device_uuid = uuid.UUID(device_id)
        except ValueError:
            logger.error("Invalid device ID format", device_id=device_id)
            return False

        # Проверка, не происходит ли уже ротация
        if self.rotation_in_progress.get(device_id, False):
            logger.debug("Rotation already in progress", device_id=device_id)
            return False

        self.rotation_in_progress[device_id] = True

        try:
            # Получение конфигурации ротации
            async with AsyncSessionLocal() as db:
                stmt = select(RotationConfig).where(
                    RotationConfig.device_id == device_uuid
                )
                result = await db.execute(stmt)
                config = result.scalar_one_or_none()

                if not config:
                    logger.error("No rotation config found", device_id=device_id)
                    return False

                # Получение информации об устройстве
                device = await self.device_manager.get_device_by_id(device_id)
                if not device:
                    logger.error("Device not found", device_id=device_id)
                    return False

                logger.info(
                    "Starting IP rotation",
                    device_id=device_id,
                    device_name=device['name'],
                    method=config.rotation_method
                )

                # Выполнение ротации в зависимости от метода
                success = False
                if config.rotation_method == 'airplane_mode':
                    success = await self.rotate_airplane_mode(device, config)
                elif config.rotation_method == 'data_toggle':
                    success = await self.rotate_data_toggle(device, config)
                elif config.rotation_method == 'network_reset':
                    success = await self.rotate_network_reset(device, config)
                elif config.rotation_method == 'api_call':
                    success = await self.rotate_api_call(device, config)

                # Обновление статистики и времени последней ротации
                await self.update_rotation_stats(device_id, success)

                if success:
                    logger.info(
                        "IP rotation completed successfully",
                        device_id=device_id,
                        device_name=device['name']
                    )

                    # Ожидание стабилизации соединения
                    await asyncio.sleep(10)

                    # Получение нового IP
                    new_ip = await self.device_manager.get_device_external_ip(device_id)
                    if new_ip:
                        logger.info(
                            "New IP obtained",
                            device_id=device_id,
                            new_ip=new_ip
                        )
                else:
                    logger.error(
                        "IP rotation failed",
                        device_id=device_id,
                        device_name=device['name']
                    )

                return success

        except Exception as e:
            logger.error(
                "Error during IP rotation",
                device_id=device_