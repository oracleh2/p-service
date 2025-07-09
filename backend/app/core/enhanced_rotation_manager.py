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
                'web_interface',      # HiLink API dial
                'hilink_reboot',      # HiLink API reboot
                'hilink_dial',        # Альтернативный HiLink dial
                'interface_restart',  # Fallback (НЕ меняет внешний IP)
                'dhcp_renew',        # Fallback (НЕ меняет внешний IP)
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

    async def rotate_device_ip(self, device_id: str, force_method: str = None) -> Tuple[bool, str]:
        """
        Универсальная ротация IP устройства с улучшенной логикой

        Args:
            device_id: UUID устройства
            force_method: Принудительный метод ротации (переопределяет конфигурацию)

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

                # Используем force_method если передан
                rotation_method = force_method or config.rotation_method

                logger.info(
                    "Starting universal IP rotation",
                    device_id=device_id,
                    device_name=device.name,
                    device_type=device.device_type,
                    requested_method=force_method,
                    config_method=config.rotation_method,
                    final_method=rotation_method
                )

                # Получаем текущий IP ДО ротации
                old_ip = await self._get_current_device_ip(device)
                logger.info(f"Current IP before rotation: {old_ip}")

                # Выполнение ротации в зависимости от типа устройства
                success, message = await self._execute_rotation(device, rotation_method)

                # Обновление статистики
                await self._update_rotation_stats(device_id, success)

                if success:
                    logger.info(
                        "IP rotation completed successfully",
                        device_id=device_id,
                        device_name=device.name,
                        method=rotation_method,
                        message=message
                    )

                    # Ожидание стабилизации соединения
                    await asyncio.sleep(self._get_stabilization_delay(device.device_type))

                    # Получение нового IP и проверка изменения
                    new_ip = await self._verify_ip_change(device, old_ip)

                    if new_ip:
                        # Обновление IP в базе данных
                        await self._update_device_ip(device_id, new_ip)
                        await self._save_ip_history(device_id, new_ip)

                        if new_ip != old_ip:
                            logger.info(
                                "New IP obtained successfully",
                                device_id=device_id,
                                old_ip=old_ip,
                                new_ip=new_ip,
                                method=rotation_method
                            )
                            return True, new_ip
                        else:
                            # IP не изменился, но ротация выполнена успешно
                            logger.info(
                                "Rotation completed but IP unchanged",
                                device_id=device_id,
                                ip=new_ip,
                                method=rotation_method
                            )
                            return True, f"Rotation completed successfully. IP unchanged: {new_ip}"
                    else:
                        # Если не удалось получить IP, пробуем fallback метод
                        fallback_method = self._get_fallback_method(device.device_type)
                        if rotation_method != fallback_method:
                            logger.warning(
                                "Could not verify IP, trying fallback method",
                                device_id=device_id,
                                current_method=rotation_method,
                                fallback_method=fallback_method
                            )

                            fallback_success, fallback_message = await self._execute_rotation(device, fallback_method)
                            if fallback_success:
                                await asyncio.sleep(self._get_stabilization_delay(device.device_type))
                                new_ip = await self._verify_ip_change(device, old_ip)
                                if new_ip:
                                    await self._update_device_ip(device_id, new_ip)
                                    await self._save_ip_history(device_id, new_ip)

                                    if new_ip != old_ip:
                                        return True, new_ip
                                    else:
                                        return True, f"Fallback rotation completed. IP unchanged: {new_ip}"

                        return False, f"Could not verify IP change after rotation"
                else:
                    logger.error(
                        "IP rotation failed",
                        device_id=device_id,
                        device_name=device.name,
                        method=rotation_method,
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

    async def _get_current_device_ip(self, device: ProxyDevice) -> Optional[str]:
        """Получение текущего IP устройства"""
        try:
            # Сначала пробуем получить из базы данных
            if device.current_external_ip:
                return device.current_external_ip

            # Если нет в БД, получаем напрямую
            return await self._force_refresh_device_external_ip(device)
        except Exception as e:
            logger.error(f"Error getting current device IP: {e}")
            return None

    async def _try_alternative_rotation_methods(self, device: ProxyDevice, failed_method: str) -> Tuple[bool, str]:
        """Попытка альтернативных методов ротации"""
        device_type = device.device_type

        # Определяем альтернативные методы в порядке приоритета
        alternative_methods = {
            'usb_modem': ['dhcp_renew', 'interface_restart', 'web_interface'],
            'android': ['data_toggle', 'airplane_mode', 'usb_reconnect'],
            'raspberry_pi': ['ppp_restart', 'gpio_reset'],
            'network_device': ['dhcp_renew', 'interface_restart']
        }

        methods_to_try = alternative_methods.get(device_type, [])

        # Убираем уже неудачный метод
        if failed_method in methods_to_try:
            methods_to_try.remove(failed_method)

        logger.info(f"Trying alternative rotation methods for {device.name}: {methods_to_try}")

        for method in methods_to_try:
            try:
                logger.info(f"Attempting alternative method: {method}")
                success, message = await self._execute_rotation(device, method)

                if success:
                    logger.info(f"Alternative method {method} succeeded: {message}")
                    return True, f"Alternative method {method} succeeded: {message}"
                else:
                    logger.warning(f"Alternative method {method} failed: {message}")

            except Exception as e:
                logger.error(f"Alternative method {method} error: {e}")
                continue

        return False, f"All alternative methods failed for {device_type}"

    async def _execute_rotation(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Выполнение ротации в зависимости от типа устройства и метода"""
        device_type = device.device_type

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
        """Ротация IP для USB модема с правильными методами для HiLink"""
        try:
            if method == 'web_interface':
                return await self._usb_modem_web_interface(device)
            elif method == 'hilink_reboot':
                return await self._usb_modem_hilink_reboot(device)
            elif method == 'hilink_dial':
                return await self._hilink_api_rotation(self._get_web_interface_from_device(device))
            elif method == 'interface_restart':
                # Оставляем как fallback метод
                return await self._usb_modem_interface_restart(device)
            elif method == 'dhcp_renew':
                # Предупреждаем что это не изменит внешний IP
                logger.warning(f"DHCP renew for HiLink modem {device.name} - this will NOT change external IP")
                result = await self._usb_modem_dhcp_renew(device)
                if result[0]:
                    return True, "DHCP renewed (Note: External IP unchanged - this is normal for HiLink modems)"
                return result
            else:
                return False, f"Unknown USB modem rotation method: {method}"
        except Exception as e:
            return False, f"USB modem rotation error: {str(e)}"

    def _get_web_interface_from_device(self, device: ProxyDevice) -> str:
        """Получение адреса веб-интерфейса из информации об устройстве"""
        try:
            device_name = device.name
            if 'huawei_' in device_name:
                interface_name = device_name.replace('huawei_', '')

                import netifaces
                if interface_name in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface_name)
                    if netifaces.AF_INET in addrs:
                        interface_ip = addrs[netifaces.AF_INET][0]['addr']
                        parts = interface_ip.split('.')
                        if len(parts) == 4 and parts[0] == '192' and parts[1] == '168':
                            subnet_number = parts[2]
                            return f"192.168.{subnet_number}.1"

            return "192.168.8.1"  # Fallback

        except Exception as e:
            logger.error(f"Error getting web interface: {e}")
            return "192.168.8.1"

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
        """
        Улучшенная проверка изменения IP адреса устройства

        Args:
            device: Устройство для проверки
            old_ip: Предыдущий IP адрес
            max_attempts: Максимальное количество попыток проверки

        Returns:
            Optional[str]: Новый IP адрес или None если не изменился
        """
        logger.info(f"Verifying IP change for device {device.name}, old IP: {old_ip}")

        for attempt in range(max_attempts):
            try:
                # Принудительно обновляем IP из менеджера
                new_ip = await self._force_refresh_device_external_ip(device)

                if new_ip:
                    logger.debug(f"Attempt {attempt + 1}: Got IP {new_ip} for device {device.name}")

                    # Проверяем изменение IP
                    if new_ip != old_ip:
                        logger.info(f"✅ IP changed from {old_ip} to {new_ip} for device {device.name}")
                        return new_ip
                    else:
                        logger.debug(f"IP unchanged: {new_ip} (attempt {attempt + 1}/{max_attempts})")

                        # Для некоторых операторов IP может не изменяться сразу
                        # Добавляем более длительное ожидание для последних попыток
                        if attempt >= 2:
                            await asyncio.sleep(8)  # Дольше ждем на последних попытках
                        else:
                            await asyncio.sleep(3)
                else:
                    logger.warning(f"Could not get IP on attempt {attempt + 1} for device {device.name}")
                    await asyncio.sleep(3)

            except Exception as e:
                logger.warning(f"IP check attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(3)

        # Если IP не изменился, это может быть нормальным поведением
        logger.info(f"IP didn't change after {max_attempts} attempts for device {device.name}")

        # Возвращаем текущий IP как "новый" если он есть
        if old_ip and old_ip != "None":
            logger.info(f"Returning current IP {old_ip} as rotation result (no change detected)")
            return old_ip

        return None

    async def _force_refresh_device_external_ip(self, device: ProxyDevice) -> Optional[str]:
        """Принудительное обновление внешнего IP устройства"""
        try:
            device_name = device.name
            device_type = device.device_type

            # Получаем внешний IP в зависимости от типа устройства
            if device_type == 'android':
                if self.device_manager:
                    # Для Android используем device_manager, но принудительно обновляем
                    android_device = await self.device_manager.get_device_by_id(device_name)
                    if android_device:
                        # Очищаем кэш если есть
                        android_device.pop('external_ip', None)
                        return await self.device_manager.get_device_external_ip(device_name)

            elif device_type == 'usb_modem':
                if hasattr(self, 'modem_manager') and self.modem_manager:
                    # Для USB модемов используем force_refresh_external_ip
                    return await self.modem_manager.force_refresh_external_ip(device_name)

            # Fallback - используем UUID
            return await self._get_device_external_ip_by_uuid(str(device.id))

        except Exception as e:
            logger.error(f"Error force refreshing external IP for device {device.name}: {e}")
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
            'android': 8,     # Сокращено с 12 до 8 секунд
            'usb_modem': 10,  # Сокращено с 20 до 10 секунд
            'raspberry_pi': 15,  # Сокращено с 25 до 15 секунд
            'network_device': 5  # Сокращено с 8 до 5 секунд
        }
        return delays.get(device_type, 10)  # По умолчанию 10 секунд вместо 15

    def _get_fallback_method(self, device_type: str) -> str:
        """Получение запасного метода ротации для HiLink модемов"""
        fallbacks = {
            'android': 'airplane_mode',
            'usb_modem': 'hilink_reboot',  # Для HiLink модемов используем перезагрузку через API
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
        """Создание конфигурации ротации по умолчанию с правильными методами"""
        default_methods = {
            'android': 'data_toggle',
            'usb_modem': 'web_interface',  # Для HiLink модемов используем веб-интерфейс
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
        """Ротация через веб-интерфейс USB модема (HiLink API)"""
        try:
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

                            logger.info(f"Attempting HiLink API rotation via {web_interface}")

                            # Реальная ротация через HiLink API
                            return await self._hilink_api_rotation(web_interface)

            return False, "Could not determine web interface for USB modem"

        except Exception as e:
            return False, f"Web interface rotation error: {str(e)}"

    async def _hilink_api_rotation(self, web_interface: str) -> Tuple[bool, str]:
        """Ротация IP через HiLink API"""
        try:
            import aiohttp
            import xml.etree.ElementTree as ET

            async with aiohttp.ClientSession() as session:
                # Шаг 1: Получаем токен сессии
                try:
                    async with session.get(
                        f"http://{web_interface}/api/webserver/SesTokInfo",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status != 200:
                            return False, f"Cannot get session token: HTTP {response.status}"

                        token_xml = await response.text()
                        logger.debug(f"Session token response: {token_xml}")

                        # Парсим XML токена
                        root = ET.fromstring(token_xml)
                        ses_info = root.find('SesInfo')
                        tok_info = root.find('TokInfo')

                        if ses_info is None or tok_info is None:
                            return False, "Invalid session token response"

                        session_id = ses_info.text
                        csrf_token = tok_info.text

                        logger.info(f"Got session token for {web_interface}")

                except Exception as e:
                    logger.error(f"Error getting session token: {e}")
                    return False, f"Cannot get session token: {str(e)}"

                # Шаг 2: Получаем статус соединения
                try:
                    headers = {
                        'Cookie': f'SessionID={session_id}',
                        '__RequestVerificationToken': csrf_token
                    }

                    async with session.get(
                        f"http://{web_interface}/api/monitoring/status",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            status_xml = await response.text()
                            logger.debug(f"Current status: {status_xml}")
                        else:
                            logger.warning(f"Cannot get status: HTTP {response.status}")

                except Exception as e:
                    logger.warning(f"Error getting status: {e}")

                # Шаг 3: Выполняем ротацию через отключение/подключение
                try:
                    # Отключаем соединение
                    disconnect_xml = '<?xml version="1.0" encoding="UTF-8"?><request><Action>0</Action></request>'

                    headers = {
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'Cookie': f'SessionID={session_id}',
                        '__RequestVerificationToken': csrf_token
                    }

                    async with session.post(
                        f"http://{web_interface}/api/dialup/dial",
                        headers=headers,
                        data=disconnect_xml,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            result_xml = await response.text()
                            logger.info(f"Disconnect result: {result_xml}")
                        else:
                            logger.warning(f"Disconnect failed: HTTP {response.status}")

                    # Ждем отключения
                    await asyncio.sleep(5)

                    # Подключаем соединение
                    connect_xml = '<?xml version="1.0" encoding="UTF-8"?><request><Action>1</Action></request>'

                    async with session.post(
                        f"http://{web_interface}/api/dialup/dial",
                        headers=headers,
                        data=connect_xml,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as response:
                        if response.status == 200:
                            result_xml = await response.text()
                            logger.info(f"Connect result: {result_xml}")
                        else:
                            logger.warning(f"Connect failed: HTTP {response.status}")

                    # Ждем подключения
                    await asyncio.sleep(10)

                    return True, "HiLink API rotation completed successfully"

                except Exception as e:
                    logger.error(f"Error during HiLink dial operation: {e}")
                    return False, f"HiLink dial operation failed: {str(e)}"

        except Exception as e:
            logger.error(f"HiLink API rotation error: {e}")
            return False, f"HiLink API rotation error: {str(e)}"

    async def _usb_modem_hilink_reboot(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Перезагрузка HiLink модема через API"""
        try:
            device_name = device.name

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

                            logger.info(f"Attempting HiLink reboot via {web_interface}")

                            return await self._hilink_api_reboot(web_interface)

            return False, "Could not determine web interface for USB modem"

        except Exception as e:
            return False, f"HiLink reboot error: {str(e)}"

    async def _hilink_api_reboot(self, web_interface: str) -> Tuple[bool, str]:
        """Перезагрузка модема через HiLink API"""
        try:
            import aiohttp
            import xml.etree.ElementTree as ET

            async with aiohttp.ClientSession() as session:
                # Получаем токен сессии
                try:
                    async with session.get(
                        f"http://{web_interface}/api/webserver/SesTokInfo",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status != 200:
                            return False, f"Cannot get session token: HTTP {response.status}"

                        token_xml = await response.text()
                        root = ET.fromstring(token_xml)
                        ses_info = root.find('SesInfo')
                        tok_info = root.find('TokInfo')

                        if ses_info is None or tok_info is None:
                            return False, "Invalid session token response"

                        session_id = ses_info.text
                        csrf_token = tok_info.text

                except Exception as e:
                    return False, f"Cannot get session token: {str(e)}"

                # Отправляем команду перезагрузки
                try:
                    reboot_xml = '<?xml version="1.0" encoding="UTF-8"?><request><Control>1</Control></request>'

                    headers = {
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'Cookie': f'SessionID={session_id}',
                        '__RequestVerificationToken': csrf_token
                    }

                    async with session.post(
                        f"http://{web_interface}/api/device/control",
                        headers=headers,
                        data=reboot_xml,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            result_xml = await response.text()
                            logger.info(f"Reboot command sent: {result_xml}")
                        else:
                            logger.warning(f"Reboot command failed: HTTP {response.status}")

                    # Ждем перезагрузки модема
                    logger.info("Waiting for modem reboot...")
                    await asyncio.sleep(30)

                    # Проверяем, что модем снова доступен
                    for attempt in range(6):  # 6 попыток по 5 секунд = 30 секунд
                        try:
                            async with session.get(
                                f"http://{web_interface}/api/monitoring/status",
                                timeout=aiohttp.ClientTimeout(total=3)
                            ) as response:
                                if response.status == 200:
                                    logger.info("Modem is back online after reboot")
                                    return True, "HiLink reboot completed successfully"
                        except:
                            pass

                        await asyncio.sleep(5)

                    return False, "Modem reboot initiated but device not responding"

                except Exception as e:
                    return False, f"Reboot command failed: {str(e)}"

        except Exception as e:
            return False, f"HiLink reboot error: {str(e)}"

    async def _usb_modem_interface_restart(self, device: ProxyDevice) -> Tuple[bool, str]:
        """ОСТОРОЖНЫЙ перезапуск интерфейса USB модема с сохранением настроек"""
        try:
            device_name = device.name

            # Извлекаем интерфейс из имени
            if 'huawei_' in device_name:
                interface_name = device_name.replace('huawei_', '')

                logger.info(f"Careful interface restart for {interface_name}")

                # ИСПРАВЛЕНИЕ: Сохраняем текущие настройки перед перезапуском
                # Получаем текущие настройки
                current_ip = None
                current_routes = []
                try:
                    import netifaces
                    if interface_name in netifaces.interfaces():
                        addrs = netifaces.ifaddresses(interface_name)
                        if netifaces.AF_INET in addrs:
                            current_ip = addrs[netifaces.AF_INET][0]['addr']
                            current_netmask = addrs[netifaces.AF_INET][0]['netmask']

                        # Получаем текущие маршруты
                        result = await asyncio.create_subprocess_exec(
                            'ip', 'route', 'show', 'dev', interface_name,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        stdout, _ = await result.communicate()
                        if result.returncode == 0:
                            current_routes = stdout.decode().strip().split('\n')
                except Exception as e:
                    logger.warning(f"Could not save current settings: {e}")

                # Только если есть критическая необходимость - перезапускаем интерфейс
                logger.warning(f"Performing interface restart for {interface_name} - this may break connectivity")

                # Отключение интерфейса на минимальное время
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'ip', 'link', 'set', interface_name, 'down',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(1)  # Минимальное время

                # Включение интерфейса
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'ip', 'link', 'set', interface_name, 'up',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(3)

                # Пытаемся восстановить настройки через DHCP
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'dhclient', '-v', interface_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(8)

                return True, "Careful interface restart completed successfully"

            return False, "Could not determine interface for USB modem"

        except Exception as e:
            return False, f"Interface restart error: {str(e)}"

    async def _usb_modem_dhcp_renew(self, device: ProxyDevice) -> Tuple[bool, str]:
        """Безопасное обновление DHCP для USB модема"""
        try:
            device_name = device.name

            # Извлекаем интерфейс из имени
            if 'huawei_' in device_name:
                interface_name = device_name.replace('huawei_', '')

                logger.info(f"Safe DHCP renew for interface {interface_name}")

                # ИСПРАВЛЕНИЕ: Безопасное обновление DHCP без освобождения lease
                # Метод 1: Попытка обновления через dhclient без -r
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'dhclient', '-v', interface_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(5)

                # Метод 2: Если не помогло, попытка через ip command
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'ip', 'addr', 'flush', 'dev', interface_name, 'scope', 'global',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(2)

                # Запрос нового IP через dhclient
                result = await asyncio.create_subprocess_exec(
                    'sudo', 'dhclient', '-v', interface_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await result.communicate()

                await asyncio.sleep(8)

                return True, "Safe DHCP renew completed successfully"

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
                if self.device_manager:
                    # Очищаем кэш и получаем свежий IP
                    android_device = await self.device_manager.get_device_by_id(device_name)
                    if android_device:
                        android_device.pop('external_ip', None)
                    return await self.device_manager.get_device_external_ip(device_name)

            elif device_type == 'usb_modem':
                if hasattr(self, 'modem_manager') and self.modem_manager:
                    return await self.modem_manager.force_refresh_external_ip(device_name)

            return None

        except Exception as e:
            logger.error(f"Error getting device external IP by UUID: {e}")
            return None

    async def get_hilink_modem_info(self, web_interface: str) -> Dict[str, Any]:
        """Получение информации о HiLink модеме"""
        try:
            import aiohttp
            import xml.etree.ElementTree as ET

            async with aiohttp.ClientSession() as session:
                # Получаем информацию об устройстве
                try:
                    async with session.get(
                        f"http://{web_interface}/api/device/information",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            device_xml = await response.text()
                            root = ET.fromstring(device_xml)

                            info = {
                                'device_name': root.find('DeviceName').text if root.find(
                                    'DeviceName') is not None else 'Unknown',
                                'hardware_version': root.find('HardwareVersion').text if root.find(
                                    'HardwareVersion') is not None else 'Unknown',
                                'software_version': root.find('SoftwareVersion').text if root.find(
                                    'SoftwareVersion') is not None else 'Unknown',
                                'web_ui_version': root.find('WebUIVersion').text if root.find(
                                    'WebUIVersion') is not None else 'Unknown',
                                'mac_address1': root.find('MacAddress1').text if root.find(
                                    'MacAddress1') is not None else 'Unknown',
                                'mac_address2': root.find('MacAddress2').text if root.find(
                                    'MacAddress2') is not None else 'Unknown',
                                'product_family': root.find('ProductFamily').text if root.find(
                                    'ProductFamily') is not None else 'Unknown',
                                'classify': root.find('Classify').text if root.find(
                                    'Classify') is not None else 'Unknown',
                                'support_mode': root.find('supportmode').text if root.find(
                                    'supportmode') is not None else 'Unknown',
                                'work_mode': root.find('workmode').text if root.find(
                                    'workmode') is not None else 'Unknown'
                            }

                            logger.info(f"HiLink device info: {info}")
                            return info

                except Exception as e:
                    logger.error(f"Error getting device info: {e}")
                    return {}

                # Получаем статус соединения
                try:
                    async with session.get(
                        f"http://{web_interface}/api/monitoring/status",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            status_xml = await response.text()
                            root = ET.fromstring(status_xml)

                            status_info = {
                                'connection_status': root.find('ConnectionStatus').text if root.find(
                                    'ConnectionStatus') is not None else 'Unknown',
                                'wifi_connection_status': root.find('WifiConnectionStatus').text if root.find(
                                    'WifiConnectionStatus') is not None else 'Unknown',
                                'signal_strength': root.find('SignalStrength').text if root.find(
                                    'SignalStrength') is not None else 'Unknown',
                                'signal_icon': root.find('SignalIcon').text if root.find(
                                    'SignalIcon') is not None else 'Unknown',
                                'current_network_type': root.find('CurrentNetworkType').text if root.find(
                                    'CurrentNetworkType') is not None else 'Unknown',
                                'current_service_domain': root.find('CurrentServiceDomain').text if root.find(
                                    'CurrentServiceDomain') is not None else 'Unknown',
                                'roaming_status': root.find('RoamingStatus').text if root.find(
                                    'RoamingStatus') is not None else 'Unknown',
                                'battery_status': root.find('BatteryStatus').text if root.find(
                                    'BatteryStatus') is not None else 'Unknown',
                                'battery_level': root.find('BatteryLevel').text if root.find(
                                    'BatteryLevel') is not None else 'Unknown',
                                'sim_status': root.find('SimStatus').text if root.find(
                                    'SimStatus') is not None else 'Unknown',
                                'wan_ip_address': root.find('WanIPAddress').text if root.find(
                                    'WanIPAddress') is not None else 'Unknown',
                                'primary_dns': root.find('PrimaryDns').text if root.find(
                                    'PrimaryDns') is not None else 'Unknown',
                                'secondary_dns': root.find('SecondaryDns').text if root.find(
                                    'SecondaryDns') is not None else 'Unknown',
                                'current_wan_state': root.find('CurrentWanState').text if root.find(
                                    'CurrentWanState') is not None else 'Unknown',
                                'current_wifi_user': root.find('CurrentWifiUser').text if root.find(
                                    'CurrentWifiUser') is not None else 'Unknown',
                                'total_wifi_user': root.find('TotalWifiUser').text if root.find(
                                    'TotalWifiUser') is not None else 'Unknown',
                                'current_download_rate': root.find('CurrentDownloadRate').text if root.find(
                                    'CurrentDownloadRate') is not None else 'Unknown',
                                'current_upload_rate': root.find('CurrentUploadRate').text if root.find(
                                    'CurrentUploadRate') is not None else 'Unknown',
                                'current_download_rate_display': root.find(
                                    'CurrentDownloadRateDisplay').text if root.find(
                                    'CurrentDownloadRateDisplay') is not None else 'Unknown',
                                'current_upload_rate_display': root.find('CurrentUploadRateDisplay').text if root.find(
                                    'CurrentUploadRateDisplay') is not None else 'Unknown',
                                'total_download': root.find('TotalDownload').text if root.find(
                                    'TotalDownload') is not None else 'Unknown',
                                'total_upload': root.find('TotalUpload').text if root.find(
                                    'TotalUpload') is not None else 'Unknown',
                                'total_connected_time': root.find('TotalConnectedTime').text if root.find(
                                    'TotalConnectedTime') is not None else 'Unknown',
                                'service_status': root.find('ServiceStatus').text if root.find(
                                    'ServiceStatus') is not None else 'Unknown',
                                'sim_lock_status': root.find('SimLockStatus').text if root.find(
                                    'SimLockStatus') is not None else 'Unknown',
                                'wan_policy': root.find('WanPolicy').text if root.find(
                                    'WanPolicy') is not None else 'Unknown',
                                'classify': root.find('Classify').text if root.find(
                                    'Classify') is not None else 'Unknown',
                                'fly_mode': root.find('flymode').text if root.find(
                                    'flymode') is not None else 'Unknown',
                                'cell_roam': root.find('cellroam').text if root.find(
                                    'cellroam') is not None else 'Unknown'
                            }

                            logger.info(f"HiLink connection status: {status_info}")
                            return status_info

                except Exception as e:
                    logger.error(f"Error getting connection status: {e}")
                    return {}

        except Exception as e:
            logger.error(f"Error getting HiLink info: {e}")
            return {}
