"""
Модуль управления ротацией IP адресов устройств
"""

import asyncio
import uuid
import aiohttp
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.device import ProxyDevice, RotationConfig, IpHistory
from app.models.request import RequestLog
from app.utils.logger import get_logger
from app.utils.system_config import get_system_config, set_system_config

logger = get_logger(__name__)


class RotationManager:
    """Менеджер ротации IP адресов"""

    def __init__(self):
        self.rotation_tasks: Dict[str, asyncio.Task] = {}
        self.rotation_in_progress: Dict[str, bool] = {}
        self.device_manager = None
        self.modem_manager = None
        self._running = False

    def set_device_manager(self, device_manager):
        """Установка менеджера устройств"""
        self.device_manager = device_manager

    def set_modem_manager(self, modem_manager):
        """Установка менеджера модемов"""
        self.modem_manager = modem_manager

    async def start(self):
        """Запуск менеджера ротации"""
        if self._running:
            logger.warning("Rotation manager already running")
            return

        self._running = True
        logger.info("Starting rotation manager")

        # Запуск задач ротации для всех активных устройств
        await self.start_all_rotation_tasks()

        # Запуск фонового мониторинга
        asyncio.create_task(self._monitor_rotation_tasks())

    async def stop(self):
        """Остановка менеджера ротации"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping rotation manager")

        # Остановка всех задач ротации
        for device_id, task in self.rotation_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self.rotation_tasks.clear()
        self.rotation_in_progress.clear()

    async def start_all_rotation_tasks(self):
        """Запуск задач ротации для всех активных устройств"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice).where(
                    ProxyDevice.status.in_(['online', 'busy'])
                )
                result = await db.execute(stmt)
                devices = result.scalars().all()

                for device in devices:
                    await self.start_device_rotation_task(str(device.id))

        except Exception as e:
            logger.error("Error starting rotation tasks", error=str(e))

    async def start_device_rotation_task(self, device_id: str):
        """Запуск задачи ротации для конкретного устройства"""
        if device_id in self.rotation_tasks:
            # Остановка существующей задачи
            task = self.rotation_tasks[device_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Запуск новой задачи
        task = asyncio.create_task(self._rotation_loop(device_id))
        self.rotation_tasks[device_id] = task

        logger.info("Started rotation task", device_id=device_id)

    async def stop_device_rotation_task(self, device_id: str):
        """Остановка задачи ротации для конкретного устройства"""
        if device_id in self.rotation_tasks:
            task = self.rotation_tasks[device_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.rotation_tasks[device_id]

        if device_id in self.rotation_in_progress:
            del self.rotation_in_progress[device_id]

        logger.info("Stopped rotation task", device_id=device_id)

    async def _monitor_rotation_tasks(self):
        """Мониторинг состояния задач ротации"""
        while self._running:
            try:
                # Проверка завершившихся задач
                completed_tasks = []
                for device_id, task in self.rotation_tasks.items():
                    if task.done():
                        completed_tasks.append(device_id)
                        if task.exception():
                            logger.error(
                                "Rotation task failed",
                                device_id=device_id,
                                error=str(task.exception())
                            )

                # Удаление завершившихся задач
                for device_id in completed_tasks:
                    del self.rotation_tasks[device_id]
                    if device_id in self.rotation_in_progress:
                        del self.rotation_in_progress[device_id]

                await asyncio.sleep(30)  # Проверка каждые 30 секунд

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in rotation tasks monitor", error=str(e))
                await asyncio.sleep(60)

    async def _rotation_loop(self, device_id: str):
        """Основной цикл ротации для устройства"""
        while self._running:
            try:
                # Получение конфигурации ротации
                async with AsyncSessionLocal() as db:
                    device_uuid = uuid.UUID(device_id)

                    # Проверка существования устройства
                    stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
                    result = await db.execute(stmt)
                    device = result.scalar_one_or_none()

                    if not device:
                        logger.warning("Device not found, stopping rotation", device_id=device_id)
                        break

                    if device.status not in ['online', 'busy']:
                        logger.debug("Device not active, skipping rotation",
                                     device_id=device_id, status=device.status)
                        await asyncio.sleep(60)
                        continue

                    # Получение конфигурации ротации
                    stmt = select(RotationConfig).where(
                        RotationConfig.device_id == device_uuid
                    )
                    result = await db.execute(stmt)
                    config = result.scalar_one_or_none()

                    if not config:
                        # Создание конфигурации по умолчанию
                        default_interval = await get_system_config('default_rotation_interval', 600)
                        config = RotationConfig(
                            device_id=device_uuid,
                            rotation_method='data_toggle',
                            rotation_interval=default_interval,
                            auto_rotation=True
                        )
                        db.add(config)
                        await db.commit()

                    if not config.auto_rotation:
                        logger.debug("Auto rotation disabled for device", device_id=device_id)
                        await asyncio.sleep(60)
                        continue

                    # Проверка времени последней ротации
                    if device.last_ip_rotation:
                        time_since_rotation = datetime.now(timezone.utc) - device.last_ip_rotation
                        if time_since_rotation.total_seconds() < config.rotation_interval:
                            sleep_time = config.rotation_interval - time_since_rotation.total_seconds()
                            await asyncio.sleep(sleep_time)
                            continue

                # Проверка глобальных настроек автоматической ротации
                auto_rotation_enabled = await get_system_config('auto_rotation_enabled', True)
                if not auto_rotation_enabled:
                    logger.debug("Auto rotation disabled globally")
                    await asyncio.sleep(300)  # Проверяем каждые 5 минут
                    continue

                # Выполнение ротации
                await self.rotate_device_ip(device_id)

                # Ожидание до следующей ротации
                await asyncio.sleep(config.rotation_interval)

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
            # Получение конфигурации ротации и информации об устройстве
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
                stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()

                if not device:
                    logger.error("Device not found", device_id=device_id)
                    return False

                logger.info(
                    "Starting IP rotation",
                    device_id=device_id,
                    device_name=device.name,
                    device_type=device.device_type,
                    method=config.rotation_method
                )

                # Сохранение старого IP для сравнения
                old_ip = device.current_external_ip

                # Выполнение ротации в зависимости от типа устройства и метода
                success = False

                if device.device_type == 'android':
                    success = await self._rotate_android_device(device, config)
                elif device.device_type == 'usb_modem':
                    success = await self._rotate_usb_modem(device, config)
                elif device.device_type == 'raspberry_pi':
                    success = await self._rotate_raspberry_pi(device, config)
                else:
                    logger.error("Unsupported device type",
                                 device_id=device_id, device_type=device.device_type)
                    return False

                # Обновление статистики и времени последней ротации
                await self._update_rotation_stats(device_id, success)

                if success:
                    logger.info(
                        "IP rotation completed successfully",
                        device_id=device_id,
                        device_name=device.name
                    )

                    # Ожидание стабилизации соединения
                    await asyncio.sleep(10)

                    # Получение нового IP
                    new_ip = await self._get_device_external_ip(device.ip_address, device.port)
                    if new_ip and new_ip != old_ip:
                        # Обновление IP в базе данных
                        await self._update_device_ip(device_id, new_ip)

                        # Сохранение в историю IP
                        await self._save_ip_history(device_id, new_ip)

                        logger.info(
                            "New IP obtained",
                            device_id=device_id,
                            old_ip=old_ip,
                            new_ip=new_ip
                        )
                    else:
                        logger.warning(
                            "Failed to obtain new IP or IP unchanged",
                            device_id=device_id,
                            old_ip=old_ip,
                            new_ip=new_ip
                        )
                else:
                    logger.error(
                        "IP rotation failed",
                        device_id=device_id,
                        device_name=device.name
                    )

                return success

        except Exception as e:
            logger.error(
                "Error during IP rotation",
                device_id=device_id,
                error=str(e)
            )
            return False
        finally:
            self.rotation_in_progress[device_id] = False

    async def _rotate_android_device(self, device: ProxyDevice, config: RotationConfig) -> bool:
        """Ротация IP для Android устройства"""
        try:
            if config.rotation_method == 'airplane_mode':
                return await self._android_airplane_mode_rotation(device)
            elif config.rotation_method == 'data_toggle':
                return await self._android_data_toggle_rotation(device)
            elif config.rotation_method == 'api_call' and config.rotation_url:
                return await self._api_call_rotation(config)
            else:
                logger.error("Unknown rotation method for Android",
                             device_id=str(device.id), method=config.rotation_method)
                return False

        except Exception as e:
            logger.error("Error in Android rotation", device_id=str(device.id), error=str(e))
            return False

    async def _rotate_usb_modem(self, device: ProxyDevice, config: RotationConfig) -> bool:
        """Ротация IP для USB модема"""
        try:
            if config.rotation_method == 'at_commands':
                return await self._usb_modem_at_commands_rotation(device)
            elif config.rotation_method == 'network_reset':
                return await self._usb_modem_network_reset(device)
            elif config.rotation_method == 'api_call' and config.rotation_url:
                return await self._api_call_rotation(config)
            else:
                logger.error("Unknown rotation method for USB modem",
                             device_id=str(device.id), method=config.rotation_method)
                return False

        except Exception as e:
            logger.error("Error in USB modem rotation", device_id=str(device.id), error=str(e))
            return False

    async def _rotate_raspberry_pi(self, device: ProxyDevice, config: RotationConfig) -> bool:
        """Ротация IP для Raspberry Pi"""
        try:
            if config.rotation_method == 'ppp_restart':
                return await self._raspberry_pi_ppp_restart(device)
            elif config.rotation_method == 'modem_reset':
                return await self._raspberry_pi_modem_reset(device)
            elif config.rotation_method == 'api_call' and config.rotation_url:
                return await self._api_call_rotation(config)
            else:
                logger.error("Unknown rotation method for Raspberry Pi",
                             device_id=str(device.id), method=config.rotation_method)
                return False

        except Exception as e:
            logger.error("Error in Raspberry Pi rotation", device_id=str(device.id), error=str(e))
            return False

    async def _android_airplane_mode_rotation(self, device: ProxyDevice) -> bool:
        """Ротация через режим полета для Android"""
        try:
            # Включение режима полета
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device.name, 'shell', 'settings', 'put', 'global', 'airplane_mode_on', '1',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Применение настроек
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device.name, 'shell', 'am', 'broadcast',
                '-a', 'android.intent.action.AIRPLANE_MODE', '--ez', 'state', 'true',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание
            await asyncio.sleep(5)

            # Отключение режима полета
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device.name, 'shell', 'settings', 'put', 'global', 'airplane_mode_on', '0',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Применение настроек
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device.name, 'shell', 'am', 'broadcast',
                '-a', 'android.intent.action.AIRPLANE_MODE', '--ez', 'state', 'false',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание восстановления соединения
            await asyncio.sleep(15)

            return True

        except Exception as e:
            logger.error("Error in airplane mode rotation", error=str(e))
            return False

    async def _android_data_toggle_rotation(self, device: ProxyDevice) -> bool:
        """Ротация через переключение мобильных данных для Android"""
        try:
            # Отключение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device.name, 'shell', 'svc', 'data', 'disable',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание
            await asyncio.sleep(3)

            # Включение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device.name, 'shell', 'svc', 'data', 'enable',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание восстановления соединения
            await asyncio.sleep(10)

            return True

        except Exception as e:
            logger.error("Error in data toggle rotation", error=str(e))
            return False

    async def _usb_modem_at_commands_rotation(self, device: ProxyDevice) -> bool:
        """Ротация через AT команды для USB модема"""
        try:
            # Определение порта модема (обычно /dev/ttyUSB0 или /dev/ttyACM0)
            modem_port = f"/dev/tty{device.name.split('_')[-1]}" if '_' in device.name else "/dev/ttyUSB0"

            # Отключение радио
            result = await asyncio.create_subprocess_exec(
                'echo', 'AT+CFUN=0', '|', 'socat', '-', f'{modem_port},crnl',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
            )
            await result.wait()

            # Ожидание
            await asyncio.sleep(5)

            # Включение радио
            result = await asyncio.create_subprocess_exec(
                'echo', 'AT+CFUN=1', '|', 'socat', '-', f'{modem_port},crnl',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
            )
            await result.wait()

            # Ожидание восстановления соединения
            await asyncio.sleep(20)

            return True

        except Exception as e:
            logger.error("Error in AT commands rotation", error=str(e))
            return False

    async def _usb_modem_network_reset(self, device: ProxyDevice) -> bool:
        """Ротация через сброс сети для USB модема"""
        try:
            # Определение сетевого интерфейса
            interface = f"wwan{device.name.split('_')[-1]}" if '_' in device.name else "wwan0"

            # Отключение интерфейса
            result = await asyncio.create_subprocess_exec(
                'sudo', 'ifdown', interface,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание
            await asyncio.sleep(5)

            # Включение интерфейса
            result = await asyncio.create_subprocess_exec(
                'sudo', 'ifup', interface,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание восстановления соединения
            await asyncio.sleep(15)

            return True

        except Exception as e:
            logger.error("Error in network reset rotation", error=str(e))
            return False

    async def _raspberry_pi_ppp_restart(self, device: ProxyDevice) -> bool:
        """Ротация через перезапуск PPP для Raspberry Pi"""
        try:
            # Остановка PPP
            result = await asyncio.create_subprocess_exec(
                'sudo', 'poff', 'provider',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание
            await asyncio.sleep(5)

            # Запуск PPP
            result = await asyncio.create_subprocess_exec(
                'sudo', 'pon', 'provider',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание восстановления соединения
            await asyncio.sleep(20)

            return True

        except Exception as e:
            logger.error("Error in PPP restart rotation", error=str(e))
            return False

    async def _raspberry_pi_modem_reset(self, device: ProxyDevice) -> bool:
        """Ротация через сброс модема для Raspberry Pi"""
        try:
            # Сброс модема через GPIO (если настроен)
            # Или через USB reset
            result = await asyncio.create_subprocess_exec(
                'sudo', 'usbreset', f'/dev/ttyUSB0',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.wait()

            # Ожидание восстановления
            await asyncio.sleep(30)

            return True

        except Exception as e:
            logger.error("Error in modem reset rotation", error=str(e))
            return False

    async def _api_call_rotation(self, config: RotationConfig) -> bool:
        """Ротация через API вызов"""
        try:
            headers = {}
            if config.auth_token:
                headers['Authorization'] = f'Bearer {config.auth_token}'

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config.rotation_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        return True
                    else:
                        logger.error("API rotation failed",
                                     status=response.status,
                                     url=config.rotation_url)
                        return False

        except Exception as e:
            logger.error("Error in API rotation", error=str(e))
            return False

    async def _get_device_external_ip(self, device_ip: str, device_port: int) -> Optional[str]:
        """Получение внешнего IP адреса устройства"""
        try:
            proxy_url = f"http://{device_ip}:{device_port}"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://httpbin.org/ip',
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('origin', '').split(',')[0].strip()
                    else:
                        return None

        except Exception as e:
            logger.error("Error getting external IP", device_ip=device_ip, error=str(e))
            return None

    async def _update_device_ip(self, device_id: str, new_ip: str):
        """Обновление IP адреса устройства в базе данных"""
        try:
            async with AsyncSessionLocal() as db:
                device_uuid = uuid.UUID(device_id)
                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == device_uuid
                ).values(
                    current_external_ip=new_ip,
                    updated_at=datetime.now(timezone.utc)
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error("Error updating device IP", device_id=device_id, error=str(e))

    async def _save_ip_history(self, device_id: str, ip_address: str):
        """Сохранение IP адреса в историю"""
        try:
            async with AsyncSessionLocal() as db:
                device_uuid = uuid.UUID(device_id)

                # Проверка, существует ли уже этот IP в истории
                stmt = select(IpHistory).where(
                    IpHistory.device_id == device_uuid,
                    IpHistory.ip_address == ip_address
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # Обновление времени последнего использования
                    stmt = update(IpHistory).where(
                        IpHistory.id == existing.id
                    ).values(
                        last_seen=datetime.now(timezone.utc),
                        total_requests=existing.total_requests + 1
                    )
                    await db.execute(stmt)
                else:
                    # Создание новой записи
                    ip_history = IpHistory(
                        device_id=device_uuid,
                        ip_address=ip_address,
                        first_seen=datetime.now(timezone.utc),
                        last_seen=datetime.now(timezone.utc),
                        total_requests=1
                    )
                    db.add(ip_history)

                await db.commit()

        except Exception as e:
            logger.error("Error saving IP history", device_id=device_id, error=str(e))

    async def _update_rotation_stats(self, device_id: str, success: bool):
        """Обновление статистики ротации"""
        try:
            async with AsyncSessionLocal() as db:
                device_uuid = uuid.UUID(device_id)

                # Обновление времени последней ротации в устройстве
                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == device_uuid
                ).values(
                    last_ip_rotation=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                await db.execute(stmt)

                # Обновление статистики в конфигурации ротации
                stmt = select(RotationConfig).where(
                    RotationConfig.device_id == device_uuid
                )
                result = await db.execute(stmt)
                config = result.scalar_one_or_none()

                if config:
                    if success:
                        # Увеличение счетчика успешных ротаций
                        total_rotations = getattr(config, 'total_rotations', 0) + 1
                        successful_rotations = getattr(config, 'successful_rotations', 0) + 1
                        success_rate = successful_rotations / total_rotations if total_rotations > 0 else 0

                        stmt = update(RotationConfig).where(
                            RotationConfig.id == config.id
                        ).values(
                            rotation_success_rate=success_rate,
                            last_successful_rotation=datetime.now(timezone.utc)
                        )
                    else:
                        # Только увеличение общего счетчика
                        total_rotations = getattr(config, 'total_rotations', 0) + 1
                        successful_rotations = getattr(config, 'successful_rotations', 0)
                        success_rate = successful_rotations / total_rotations if total_rotations > 0 else 0

                        stmt = update(RotationConfig).where(
                            RotationConfig.id == config.id
                        ).values(
                            rotation_success_rate=success_rate
                        )

                    await db.execute(stmt)

                await db.commit()

        except Exception as e:
            logger.error("Error updating rotation stats", device_id=device_id, error=str(e))

    async def rotate_modem_ip(self, modem_id: str) -> bool:
        """Ротация IP модема через modem_manager"""
        try:
            if not self.modem_manager:
                logger.error("Modem manager not available")
                return False

            return await self.modem_manager.rotate_modem_ip(modem_id)

        except Exception as e:
            logger.error("Error rotating modem IP", modem_id=modem_id, error=str(e))
            return False

    async def rotate_all_modems(self) -> Dict[str, bool]:
        """Ротация IP всех модемов"""
        try:
            if not self.modem_manager:
                logger.error("Modem manager not available")
                return {}

            modems = await self.modem_manager.get_all_modems()
            results = {}

            for modem_id in modems.keys():
                success = await self.rotate_modem_ip(modem_id)
                results[modem_id] = success

            return results

        except Exception as e:
            logger.error("Error rotating all modems", error=str(e))
            return {}

    async def get_rotation_status(self, device_id: str) -> Dict[str, Any]:
        """Получение статуса ротации устройства"""
        try:
            async with AsyncSessionLocal() as db:
                device_uuid = uuid.UUID(device_id)

                # Получение информации об устройстве
                stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()

                if not device:
                    return {"error": "Device not found"}

                # Получение конфигурации ротации
                stmt = select(RotationConfig).where(
                    RotationConfig.device_id == device_uuid
                )
                result = await db.execute(stmt)
                config = result.scalar_one_or_none()

                is_rotating = self.rotation_in_progress.get(device_id, False)
                has_task = device_id in self.rotation_tasks

                return {
                    "device_id": device_id,
                    "device_name": device.name,
                    "auto_rotation": config.auto_rotation if config else False,
                    "rotation_interval": config.rotation_interval if config else 600,
                    "rotation_method": config.rotation_method if config else "data_toggle",
                    "last_rotation": device.last_ip_rotation.isoformat() if device.last_ip_rotation else None,
                    "rotation_in_progress": is_rotating,
                    "rotation_task_active": has_task,
                    "current_ip": device.current_external_ip,
                    "success_rate": config.rotation_success_rate if config else 0.0
                }

        except Exception as e:
            logger.error("Error getting rotation status", device_id=device_id, error=str(e))
            return {"error": str(e)}


# Глобальный экземпляр менеджера ротации
_rotation_manager: Optional[RotationManager] = None


def get_rotation_manager() -> Optional[RotationManager]:
    """Получение глобального экземпляра менеджера ротации"""
    return _rotation_manager


def set_rotation_manager(manager: RotationManager):
    """Установка глобального экземпляра менеджера ротации"""
    global _rotation_manager
    _rotation_manager = manager
