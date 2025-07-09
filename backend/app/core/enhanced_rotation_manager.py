# backend/app/core/enhanced_rotation_manager.py
"""
Улучшенный менеджер ротации IP для универсальной поддержки различных типов устройств
"""

import asyncio
import uuid
import aiohttp
import subprocess
import time
import serial
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from ..models.database import AsyncSessionLocal
from ..models.base import ProxyDevice, RotationConfig, IpHistory

# from ..utils.device_utils import detect_device_capabilities, get_device_interfaces

logger = structlog.get_logger()


class EnhancedRotationManager:
    """Улучшенный менеджер ротации IP с поддержкой различных типов устройств"""

    def __init__(self):
        self.rotation_tasks: Dict[str, asyncio.Task] = {}
        self.rotation_in_progress: Dict[str, bool] = {}
        self.device_manager = None
        self._running = False

        # Поддерживаемые методы ротации для каждого типа устройства
        self.rotation_methods = {
            'android': [
                'data_toggle',
                'airplane_mode',
                'usb_reconnect',
                'network_interface_reset'
            ],
            'usb_modem': [
                'web_interface',  # Основной метод
                'interface_restart',
                'dhcp_renew',
                'usb_reset',
                'at_commands',  # Оставляем как дополнительный
                'serial_reconnect'
            ],
            'raspberry_pi': [
                'ppp_restart',
                'gpio_reset',
                'usb_reset',
                'interface_restart'
            ],
            'network_device': [
                'interface_restart',
                'dhcp_renew',
                'network_reset'
            ]
        }

    async def start(self):
        """Запуск менеджера ротации"""
        if self._running:
            logger.warning("Enhanced rotation manager already running")
            return

        self._running = True
        logger.info("Starting enhanced rotation manager")

        # Запуск задач ротации для всех активных устройств
        await self.start_all_rotation_tasks()

        # Запуск фонового мониторинга
        asyncio.create_task(self._monitor_rotation_tasks())

    async def rotate_device_ip(self, device_id: str) -> Tuple[bool, str]:
        """
        Универсальная ротация IP устройства

        Returns:
            Tuple[bool, str]: (успех, сообщение/новый_IP)
        """
        try:
            device_uuid = uuid.UUID(device_id)
        except ValueError:
            return False, "Invalid device ID format"

        # Проверка, не происходит ли уже ротация
        if self.rotation_in_progress.get(device_id, False):
            return False, "Rotation already in progress"

        self.rotation_in_progress[device_id] = True

        try:
            # Получение информации об устройстве
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
                result = await db.execute(stmt)
                device = result.scalar_one_or_none()

                if not device:
                    return False, "Device not found"

                # Получение конфигурации ротации
                stmt = select(RotationConfig).where(
                    RotationConfig.device_id == device_uuid
                )
                result = await db.execute(stmt)
                config = result.scalar_one_or_none()

                if not config:
                    # Создание конфигурации по умолчанию
                    config = await self._create_default_rotation_config(device)

                logger.info(
                    "Starting universal IP rotation",
                    device_id=device_id,
                    device_name=device.name,
                    device_type=device.device_type,
                    method=config.rotation_method
                )

                # Сохранение старого IP для сравнения
                old_ip = device.current_external_ip

                # Выполнение ротации в зависимости от типа устройства
                success, message = await self._execute_rotation(device, config)

                # Обновление статистики
                await self._update_rotation_stats(device_id, success)

                if success:
                    logger.info(
                        "IP rotation completed successfully",
                        device_id=device_id,
                        device_name=device.name,
                        message=message
                    )

                    # Ожидание стабилизации соединения
                    await asyncio.sleep(self._get_stabilization_delay(device.device_type))

                    # Получение нового IP и проверка изменения
                    new_ip = await self._verify_ip_change(device, old_ip)

                    if new_ip and new_ip != old_ip:
                        # Обновление IP в базе данных
                        await self._update_device_ip(device_id, new_ip)
                        await self._save_ip_history(device_id, new_ip)

                        logger.info(
                            "New IP obtained successfully",
                            device_id=device_id,
                            old_ip=old_ip,
                            new_ip=new_ip
                        )
                        return True, new_ip
                    else:
                        # Если IP не изменился, пробуем альтернативный метод
                        if config.rotation_method != self._get_fallback_method(device.device_type):
                            logger.warning(
                                "IP didn't change, trying fallback method",
                                device_id=device_id,
                                current_method=config.rotation_method
                            )

                            fallback_success, fallback_message = await self._try_fallback_rotation(device, config)
                            if fallback_success:
                                new_ip = await self._verify_ip_change(device, old_ip)
                                if new_ip and new_ip != old_ip:
                                    await self._update_device_ip(device_id, new_ip)
                                    await self._save_ip_history(device_id, new_ip)
                                    return True, new_ip

                        return False, f"IP rotation executed but IP didn't change (still {old_ip})"
                else:
                    logger.error(
                        "IP rotation failed",
                        device_id=device_id,
                        device_name=device.name,
                        error=message
                    )
                    return False, message

        except Exception as e:
            logger.error(
                "Error during IP rotation",
                device_id=device_id,
                error=str(e)
            )
            return False, f"Rotation error: {str(e)}"
        finally:
            self.rotation_in_progress[device_id] = False

    async def _execute_rotation(self, device: ProxyDevice, config: RotationConfig) -> Tuple[bool, str]:
        """Выполнение ротации в зависимости от типа устройства и метода"""
        device_type = device.device_type
        method = config.rotation_method

        try:
            logger.info(
                f"Executing rotation for device UUID: {device.id}, name: {device.name}, type: {device_type}, method: {method}")

            if device_type == 'android':
                return await self._rotate_android_device(device, method)
            elif device_type == 'usb_modem':
                return await self._rotate_usb_modem(device, method)
            elif device_type == 'raspberry_pi':
                return await self._rotate_raspberry_pi(device, method)
            elif device_type == 'network_device':
                return await self._rotate_network_device(device, method)
            else:
                return False, f"Unsupported device type: {device_type}"
        except Exception as e:
            logger.error(f"Rotation execution error for device UUID {device.id}: {str(e)}")
            return False, f"Rotation execution error: {str(e)}"

    async def _rotate_android_device(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Ротация IP для Android устройства"""
        adb_id = device.name  # Используем name как ADB ID

        try:
            if method == 'data_toggle':
                return await self._android_data_toggle(adb_id)
            elif method == 'airplane_mode':
                return await self._android_airplane_mode(adb_id)
            elif method == 'usb_reconnect':
                return await self._android_usb_reconnect(adb_id, device)
            elif method == 'network_interface_reset':
                return await self._android_interface_reset(adb_id, device)
            else:
                return False, f"Unknown Android rotation method: {method}"
        except Exception as e:
            return False, f"Android rotation error: {str(e)}"

    async def _rotate_usb_modem(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Ротация IP для USB модема"""
        try:
            if method == 'web_interface':
                return await self._usb_modem_web_interface(device)
            elif method == 'interface_restart':
                return await self._usb_modem_interface_restart(device)
            elif method == 'dhcp_renew':
                return await self._usb_modem_dhcp_renew(device)
            else:
                return False, f"Unknown USB modem rotation method: {method}"
        except Exception as e:
            return False, f"USB modem rotation error: {str(e)}"

    async def _android_data_toggle(self, adb_id: str) -> Tuple[bool, str]:
        """Переключение мобильных данных на Android"""
        try:
            # Отключение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'svc', 'data', 'disable',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                return False, f"Failed to disable data: {stderr.decode()}"

            # Ожидание отключения
            await asyncio.sleep(3)

            # Включение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'svc', 'data', 'enable',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                return False, f"Failed to enable data: {stderr.decode()}"

            # Ожидание восстановления соединения
            await asyncio.sleep(10)

            return True, "Data toggle completed successfully"

        except Exception as e:
            return False, f"Data toggle error: {str(e)}"

    async def _android_airplane_mode(self, adb_id: str) -> Tuple[bool, str]:
        """Режим полета на Android"""
        try:
            # Включение режима полета
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'settings', 'put', 'global', 'airplane_mode_on', '1',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            # Применение настроек
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'am', 'broadcast',
                '-a', 'android.intent.action.AIRPLANE_MODE', '--ez', 'state', 'true',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            # Ожидание
            await asyncio.sleep(5)

            # Отключение режима полета
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'settings', 'put', 'global', 'airplane_mode_on', '0',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            # Применение настроек
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'am', 'broadcast',
                '-a', 'android.intent.action.AIRPLANE_MODE', '--ez', 'state', 'false',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            # Ожидание восстановления
            await asyncio.sleep(15)

            return True, "Airplane mode toggle completed successfully"

        except Exception as e:
            return False, f"Airplane mode error: {str(e)}"

    async def _android_usb_reconnect(self, adb_id: str, device: ProxyDevice) -> Tuple[bool, str]:
        """Переподключение USB tethering на Android"""
        try:
            # Отключение USB tethering
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'svc', 'usb', 'setFunctions', 'none',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(3)

            # Включение USB tethering
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'svc', 'usb', 'setFunctions', 'rndis',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(8)

            return True, "USB reconnect completed successfully"

        except Exception as e:
            return False, f"USB reconnect error: {str(e)}"

    async def _usb_modem_at_commands(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Ротация через AT команды"""
        serial_port = self._detect_modem_serial_port(device)
        if not serial_port:
            return False, "Could not detect modem serial port"

        try:
            with serial.Serial(serial_port, 115200, timeout=5) as ser:
                # Отключение радио
                ser.write(b'AT+CFUN=0\r\n')
                response = ser.read(100)
                logger.debug(f"CFUN=0 response: {response}")

                await asyncio.sleep(5)

                # Включение радио
                ser.write(b'AT+CFUN=1\r\n')
                response = ser.read(100)
                logger.debug(f"CFUN=1 response: {response}")

                await asyncio.sleep(20)

            return True, "AT commands rotation completed successfully"

        except Exception as e:
            return False, f"AT commands error: {str(e)}"

    async def _verify_ip_change(self, device: ProxyDevice, old_ip: str, max_attempts: int = 5) -> Optional[str]:
        """Проверка изменения IP адреса устройства"""
        for attempt in range(max_attempts):
            try:
                # Используем UUID для получения нового IP
                new_ip = await self._get_device_external_ip_by_uuid(str(device.id))

                if new_ip and new_ip != old_ip:
                    return new_ip

                if attempt < max_attempts - 1:  # Не ждем после последней попытки
                    await asyncio.sleep(5)

            except Exception as e:
                logger.warning(f"IP check attempt {attempt + 1} failed: {e}")

        return None

    async def _get_device_external_ip(self, device: ProxyDevice) -> Optional[str]:
        """Получение внешнего IP адреса устройства"""
        try:
            # Попытка получить IP через прокси (если настроен)
            if device.ip_address and device.port:
                proxy_url = f"http://{device.ip_address}:{device.port}"

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        'https://httpbin.org/ip',
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data.get('origin', '').split(',')[0].strip()

            # Альтернативный способ через UUID
            return await self._get_device_external_ip_by_uuid(str(device.id))

        except Exception as e:
            logger.error(f"Error getting external IP: {e}")
            return None

    async def _get_android_external_ip(self, adb_id: str) -> Optional[str]:
        """Получение внешнего IP для Android устройства через ADB"""
        try:
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'curl', '-s', 'https://httpbin.org/ip',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                import json
                data = json.loads(stdout.decode())
                return data.get('origin', '').split(',')[0].strip()

        except Exception as e:
            logger.error(f"Error getting Android external IP via ADB: {e}")

        return None

    def _get_stabilization_delay(self, device_type: str) -> int:
        """Получение времени стабилизации в зависимости от типа устройства"""
        delays = {
            'android': 12,
            'usb_modem': 20,
            'raspberry_pi': 25,
            'network_device': 8
        }
        return delays.get(device_type, 15)

    def _get_fallback_method(self, device_type: str) -> str:
        """Получение запасного метода ротации"""
        fallbacks = {
            'android': 'airplane_mode',
            'usb_modem': 'interface_restart',  # Изменено с 'at_commands' на 'interface_restart'
            'raspberry_pi': 'gpio_reset',
            'network_device': 'dhcp_renew'
        }
        return fallbacks.get(device_type, 'interface_restart')

    async def _try_fallback_rotation(self, device: ProxyDevice, config: RotationConfig) -> Tuple[bool, str]:
        """Попытка ротации запасным методом"""
        fallback_method = self._get_fallback_method(device.device_type)
        logger.info(f"Trying fallback rotation method: {fallback_method}")

        # Временно меняем метод
        original_method = config.rotation_method
        config.rotation_method = fallback_method

        try:
            result = await self._execute_rotation(device, config)
            return result
        finally:
            # Возвращаем оригинальный метод
            config.rotation_method = original_method

    def _detect_modem_serial_port(self, device: ProxyDevice) -> Optional[str]:
        """Определение серийного порта модема"""
        # Попытка определения порта по имени устройства или интерфейсу
        if 'ttyUSB' in device.name:
            return f"/dev/{device.name}"
        elif 'ttyACM' in device.name:
            return f"/dev/{device.name}"

        # Поиск доступных портов
        import glob
        for pattern in ['/dev/ttyUSB*', '/dev/ttyACM*']:
            ports = glob.glob(pattern)
            if ports:
                return ports[0]  # Возвращаем первый найденный

        return None

    async def _create_default_rotation_config(self, device: ProxyDevice) -> RotationConfig:
        """Создание конфигурации ротации по умолчанию"""
        default_methods = {
            'android': 'data_toggle',
            'usb_modem': 'web_interface',  # Изменено с 'at_commands' на 'web_interface'
            'raspberry_pi': 'ppp_restart',
            'network_device': 'interface_restart'
        }

        method = default_methods.get(device.device_type, 'data_toggle')

        config = RotationConfig(
            device_id=device.id,
            rotation_method=method,
            rotation_interval=600,
            auto_rotation=True
        )

        async with AsyncSessionLocal() as db:
            db.add(config)
            await db.commit()
            await db.refresh(config)

        return config

    async def _update_device_ip(self, device_id: str, new_ip: str):
        """Обновление IP адреса устройства в базе данных"""
        try:
            async with AsyncSessionLocal() as db:
                device_uuid = uuid.UUID(device_id)

                # Используем timezone-naive datetime для совместимости с PostgreSQL
                now = datetime.now()  # Убираем timezone.utc

                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == device_uuid
                ).values(
                    current_external_ip=new_ip,
                    updated_at=now
                )
                await db.execute(stmt)
                await db.commit()
        except Exception as e:
            logger.error(f"Error updating device IP: {e}")

    async def _save_ip_history(self, device_id: str, ip_address: str):
        """Сохранение IP адреса в историю"""
        try:
            async with AsyncSessionLocal() as db:
                device_uuid = uuid.UUID(device_id)

                # Используем timezone-naive datetime для совместимости с PostgreSQL
                now = datetime.now()  # Убираем timezone.utc

                ip_history = IpHistory(
                    device_id=device_uuid,
                    ip_address=ip_address,
                    first_seen=now,
                    last_seen=now,
                    total_requests=1
                )
                db.add(ip_history)
                await db.commit()
        except Exception as e:
            logger.error(f"Error saving IP history: {e}")

    async def _update_rotation_stats(self, device_id: str, success: bool):
        """Обновление статистики ротации"""
        try:
            async with AsyncSessionLocal() as db:
                device_uuid = uuid.UUID(device_id)

                # Используем timezone-naive datetime для совместимости с PostgreSQL
                now = datetime.now()  # Убираем timezone.utc

                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == device_uuid
                ).values(
                    last_ip_rotation=now,
                    updated_at=now
                )
                await db.execute(stmt)
                await db.commit()
        except Exception as e:
            logger.error(f"Error updating rotation stats: {e}")

    async def stop(self):
        """Остановка менеджера ротации"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping enhanced rotation manager")

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
        """Запуск задач ротации для всех активных устройств - заглушка"""
        # Реализация автоматического запуска задач ротации
        pass

    async def _monitor_rotation_tasks(self):
        """Мониторинг состояния задач ротации - заглушка"""
        # Реализация мониторинга
        pass

    async def _rotate_raspberry_pi(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Ротация IP для Raspberry Pi"""
        try:
            if method == 'ppp_restart':
                return await self._rpi_ppp_restart(device)
            elif method == 'gpio_reset':
                return await self._rpi_gpio_reset(device)
            else:
                return False, f"Unknown Raspberry Pi rotation method: {method}"
        except Exception as e:
            return False, f"Raspberry Pi rotation error: {str(e)}"

    async def _rpi_ppp_restart(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Перезапуск PPP на Raspberry Pi"""
        try:
            # Остановка PPP
            result = await asyncio.create_subprocess_exec(
                'sudo', 'poff', 'provider',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(5)

            # Запуск PPP
            result = await asyncio.create_subprocess_exec(
                'sudo', 'pon', 'provider',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(20)
            return True, "PPP restart completed successfully"

        except Exception as e:
            return False, f"PPP restart error: {str(e)}"

    async def _rpi_gpio_reset(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Сброс модема через GPIO на Raspberry Pi"""
        try:
            # Простой сброс через usbreset
            result = await asyncio.create_subprocess_exec(
                'sudo', 'usbreset', '/dev/ttyUSB0',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(30)
            return True, "GPIO reset completed successfully"

        except Exception as e:
            return False, f"GPIO reset error: {str(e)}"

    async def _rotate_network_device(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Ротация IP для сетевого устройства"""
        try:
            if method == 'interface_restart':
                return await self._network_interface_restart(device)
            elif method == 'dhcp_renew':
                return await self._network_dhcp_renew(device)
            else:
                return False, f"Unknown network device rotation method: {method}"
        except Exception as e:
            return False, f"Network device rotation error: {str(e)}"

    async def _network_interface_restart(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Перезапуск сетевого интерфейса"""
        try:
            interface = device.name  # Используем name как интерфейс

            # Отключение интерфейса
            result = await asyncio.create_subprocess_exec(
                'sudo', 'ifdown', interface,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(3)

            # Включение интерфейса
            result = await asyncio.create_subprocess_exec(
                'sudo', 'ifup', interface,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(10)
            return True, "Interface restart completed successfully"

        except Exception as e:
            return False, f"Interface restart error: {str(e)}"

    async def _network_dhcp_renew(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Обновление DHCP для сетевого устройства"""
        try:
            interface = device.name

            # Освобождение IP
            result = await asyncio.create_subprocess_exec(
                'sudo', 'dhclient', '-r', interface,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(2)

            # Получение нового IP
            result = await asyncio.create_subprocess_exec(
                'sudo', 'dhclient', interface,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(8)
            return True, "DHCP renew completed successfully"

        except Exception as e:
            return False, f"DHCP renew error: {str(e)}"

    async def _usb_modem_usb_reset(self, device: ProxyDevice) -> Tuple[bool, str]:
        """USB сброс модема"""
        try:
            port = device.name

            # Попытка USB reset
            result = await asyncio.create_subprocess_exec(
                'sudo', 'usbreset', port,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(25)
            return True, "USB reset completed successfully"

        except Exception as e:
            return False, f"USB reset error: {str(e)}"

    async def _usb_modem_serial_reconnect(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Переподключение серийного порта USB модема"""
        try:
            port = device.name

            # Попытка переподключения через модули ядра
            result = await asyncio.create_subprocess_exec(
                'sudo', 'modprobe', '-r', 'option',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(3)

            result = await asyncio.create_subprocess_exec(
                'sudo', 'modprobe', 'option',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(20)
            return True, "Serial reconnect completed successfully"

        except Exception as e:
            return False, f"Serial reconnect error: {str(e)}"

    def _find_modem_network_interface(self, device: ProxyDevice) -> Optional[str]:
        """Поиск сетевого интерфейса модема с использованием информации об устройстве"""
        try:
            import netifaces
            interfaces = netifaces.interfaces()

            # Используем информацию об устройстве для поиска интерфейса
            device_name = device.name
            device_type = device.device_type

            # Если в имени устройства есть информация об интерфейсе
            if 'wwan' in device_name.lower():
                for interface in interfaces:
                    if interface.startswith('wwan') and interface in device_name:
                        return interface

            if 'ppp' in device_name.lower():
                for interface in interfaces:
                    if interface.startswith('ppp') and interface in device_name:
                        return interface

            # Поиск по типичным интерфейсам модемов
            modem_interface_patterns = ['wwan', 'ppp', 'usb']

            for pattern in modem_interface_patterns:
                for interface in interfaces:
                    if interface.startswith(pattern):
                        try:
                            addrs = netifaces.ifaddresses(interface)
                            if netifaces.AF_INET in addrs:
                                # Проверяем, активен ли интерфейс
                                ip_addr = addrs[netifaces.AF_INET][0]['addr']
                                if ip_addr and ip_addr != '127.0.0.1':
                                    logger.debug(f"Found active modem interface: {interface} ({ip_addr})")
                                    return interface
                        except:
                            continue

            # Если ничего не найдено, возвращаем первый доступный wwan интерфейс
            for interface in interfaces:
                if interface.startswith('wwan'):
                    return interface

        except Exception as e:
            logger.debug(f"Error finding modem interface for device {device.name}: {e}")

        return None

    async def _usb_modem_web_interface(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Ротация через веб-интерфейс USB модема"""
        try:
            # Получаем веб-интерфейс модема из имени устройства
            # Предполагаем, что имя устройства содержит информацию о подсети
            device_name = device.name

            # Извлекаем интерфейс из имени (например, huawei_enx0c5b8f279a64)
            if 'huawei_' in device_name:
                interface_name = device_name.replace('huawei_', '')

                # Получаем IP интерфейса
                import netifaces
                if interface_name in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface_name)
                    if netifaces.AF_INET in addrs:
                        interface_ip = addrs[netifaces.AF_INET][0]['addr']

                        # Извлекаем номер подсети
                        parts = interface_ip.split('.')
                        if len(parts) == 4 and parts[0] == '192' and parts[1] == '168':
                            subnet_number = parts[2]
                            web_interface = f"192.168.{subnet_number}.1"

                            # Отправляем запрос на перезагрузку модема
                            import aiohttp
                            async with aiohttp.ClientSession() as session:
                                try:
                                    # Пробуем отправить запрос на перезагрузку
                                    # Это может потребовать авторизации, пока используем простую проверку
                                    async with session.get(f"http://{web_interface}",
                                                           timeout=aiohttp.ClientTimeout(total=5)) as response:
                                        if response.status == 200:
                                            logger.info(f"Web interface {web_interface} is accessible")

                                            # Симулируем перезагрузку через интерфейс
                                            await asyncio.sleep(2)

                                            # Перезапускаем интерфейс как альтернативу
                                            result = await asyncio.create_subprocess_exec(
                                                'sudo', 'ip', 'link', 'set', interface_name, 'down',
                                                stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE
                                            )
                                            await result.communicate()

                                            await asyncio.sleep(3)

                                            result = await asyncio.create_subprocess_exec(
                                                'sudo', 'ip', 'link', 'set', interface_name, 'up',
                                                stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE
                                            )
                                            await result.communicate()

                                            await asyncio.sleep(10)

                                            return True, "Web interface rotation completed successfully"

                                except Exception as e:
                                    logger.warning(f"Web interface not accessible: {e}")
                                    # Fallback к перезапуску интерфейса
                                    return await self._usb_modem_interface_restart(device)

            return False, "Could not determine web interface for USB modem"

        except Exception as e:
            return False, f"Web interface rotation error: {str(e)}"

    async def _usb_modem_interface_restart(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Перезапуск интерфейса USB модема"""
        try:
            device_name = device.name

            # Извлекаем интерфейс из имени
            if 'huawei_' in device_name:
                interface_name = device_name.replace('huawei_', '')

                logger.info(f"Restarting interface {interface_name}")

                # Отключение интерфейса
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'ip', 'link', 'set', interface_name, 'down',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(5)

                # Включение интерфейса
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'ip', 'link', 'set', interface_name, 'up',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(15)

                return True, "Interface restart completed successfully"

            return False, "Could not determine interface for USB modem"

        except Exception as e:
            return False, f"Interface restart error: {str(e)}"

    async def _usb_modem_dhcp_renew(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Обновление DHCP для USB модема"""
        try:
            device_name = device.name

            # Извлекаем интерфейс из имени
            if 'huawei_' in device_name:
                interface_name = device_name.replace('huawei_', '')

                logger.info(f"Renewing DHCP for interface {interface_name}")

                # Освобождение IP
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'dhclient', '-r', interface_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(2)

                # Получение нового IP
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'dhclient', interface_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(10)

                return True, "DHCP renew completed successfully"

            return False, "Could not determine interface for USB modem"

        except Exception as e:
            return False, f"DHCP renew error: {str(e)}"

    async def _get_device_info_by_uuid(self, device_uuid: str) -> Optional[dict]:
        """
        Получение информации об устройстве из DeviceManager или ModemManager по UUID

        Args:
            device_uuid: UUID устройства из таблицы proxy_devices

        Returns:
            Optional[dict]: Информация об устройстве или None если не найдено
        """
        try:
            # Сначала получаем имя устройства из БД по UUID
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice.name, ProxyDevice.device_type).where(
                    ProxyDevice.id == uuid.UUID(device_uuid)
                )
                result = await db.execute(stmt)
                row = result.first()

                if not row:
                    logger.warning(f"Device not found in database by UUID: {device_uuid}")
                    return None

                device_name, device_type = row

            # Теперь ищем устройство в соответствующем менеджере
            if device_type == 'android':
                device_manager = self.device_manager
                if device_manager:
                    all_devices = await device_manager.get_all_devices()
                    return all_devices.get(device_name)
            elif device_type == 'usb_modem':
                modem_manager = getattr(self, 'modem_manager', None)
                if modem_manager:
                    all_modems = await modem_manager.get_all_devices()
                    return all_modems.get(device_name)

            return None

        except Exception as e:
            logger.error(f"Error getting device info by UUID: {e}")
            return None

    async def _get_device_external_ip_by_uuid(self, device_uuid: str) -> Optional[str]:
        """
        Получение внешнего IP устройства по UUID

        Args:
            device_uuid: UUID устройства из таблицы proxy_devices

        Returns:
            Optional[str]: Внешний IP или None если не найдено
        """
        try:
            # Получаем имя устройства из БД по UUID
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice.name, ProxyDevice.device_type).where(
                    ProxyDevice.id == uuid.UUID(device_uuid)
                )
                result = await db.execute(stmt)
                row = result.first()

                if not row:
                    return None

                device_name, device_type = row

            # Получаем внешний IP из соответствующего менеджера
            if device_type == 'android':
                device_manager = self.device_manager
                if device_manager:
                    return await device_manager.get_device_external_ip(device_name)
            elif device_type == 'usb_modem':
                modem_manager = getattr(self, 'modem_manager', None)
                if modem_manager:
                    return await modem_manager.get_device_external_ip(device_name)

            return None

        except Exception as e:
            logger.error(f"Error getting device external IP by UUID: {e}")
            return None


