# backend/app/core/enhanced_rotation_manager.py - ОБНОВЛЕННАЯ ВЕРСИЯ С USB ПЕРЕЗАГРУЗКОЙ

import asyncio
import subprocess
import uuid
import time
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from ..models.database import AsyncSessionLocal
from ..models.base import ProxyDevice, RotationConfig, IpHistory

logger = structlog.get_logger()


class EnhancedRotationManager:
    """Улучшенный менеджер ротации IP с USB перезагрузкой для Huawei E3372h модемов"""

    def __init__(self):
        self.rotation_tasks: Dict[str, asyncio.Task] = {}
        self.rotation_in_progress: Dict[str, bool] = {}
        self.device_manager = None
        self.modem_manager = None
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
                'usb_reboot',  # ЕДИНСТВЕННЫЙ метод для E3372h
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
        logger.info("Starting enhanced rotation manager with USB reboot support")

        # Запуск задач ротации для всех активных устройств
        await self.start_all_rotation_tasks()

        # Запуск фонового мониторинга
        asyncio.create_task(self._monitor_rotation_tasks())

    # backend/app/core/enhanced_rotation_manager.py - ИСПРАВЛЕННАЯ ВЕРСИЯ МЕТОДОВ РОТАЦИИ

    async def _create_default_rotation_config(self, device: ProxyDevice) -> RotationConfig:
        """Создание конфигурации ротации по умолчанию с правильными методами"""
        default_methods = {
            'android': 'data_toggle',
            'usb_modem': 'usb_reboot',  # ТОЛЬКО USB ПЕРЕЗАГРУЗКА для модемов
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

    # Поддерживаемые методы ротации для каждого типа устройства


    async def rotate_device_ip(self, device_id: str, force_method: str = None) -> Tuple[bool, str]:
        """
        Универсальная ротация IP устройства с поддержкой USB перезагрузки

        Args:
            device_id: UUID устройства
            force_method: Принудительный метод ротации (для E3372h всегда usb_reboot)

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

                # Для USB модемов E3372h используем только USB перезагрузку
                if device.device_type == 'usb_modem':
                    rotation_method = 'usb_reboot'
                else:
                    rotation_method = force_method or config.rotation_method

                logger.info(
                    "Starting IP rotation with USB reboot",
                    device_id=device_id,
                    device_name=device.name,
                    device_type=device.device_type,
                    rotation_method=rotation_method
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
                            logger.info(
                                "Rotation completed but IP unchanged",
                                device_id=device_id,
                                ip=new_ip,
                                method=rotation_method
                            )
                            return True, f"Rotation completed successfully. IP unchanged: {new_ip}"
                    else:
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

    async def _execute_rotation(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Выполнение ротации в зависимости от типа устройства и метода"""
        device_type = device.device_type

        try:
            logger.info(
                f"Executing rotation for device UUID: {device.id}, name: {device.name}, type: {device_type}, method: {method}")

            if device_type == 'android':
                return await self._rotate_android_device(device, method)
            elif device_type == 'usb_modem':
                # Для USB модемов используем только USB перезагрузку
                return await self._rotate_usb_modem_via_reboot(device)
            elif device_type == 'raspberry_pi':
                return await self._rotate_raspberry_pi(device, method)
            elif device_type == 'network_device':
                return await self._rotate_network_device(device, method)
            else:
                return False, f"Unsupported device type: {device_type}"
        except Exception as e:
            logger.error(f"Rotation execution error for device UUID {device.id}: {str(e)}")
            return False, f"Rotation execution error: {str(e)}"

    async def _rotate_usb_modem_via_reboot(self, device: ProxyDevice) -> Tuple[bool, str]:
        """
        Ротация IP для USB модема через USB перезагрузку
        Основан на bash скрипте для быстрой перезагрузки модема
        """
        try:
            device_name = device.name
            logger.info(f"Starting USB reboot rotation for device: {device_name}")

            # Получаем интерфейс модема
            interface = await self._get_modem_interface(device_name)
            if not interface:
                return False, "Could not determine modem interface"

            # Получаем текущий внешний IP
            old_external_ip = await self._get_external_ip_via_interface(interface)
            logger.info(f"External IP before USB reboot: {old_external_ip}")

            # Выполняем USB перезагрузку
            reboot_success, reboot_message = await self._perform_usb_reboot()

            if not reboot_success:
                return False, f"USB reboot failed: {reboot_message}"

            # Мониторинг перезагрузки
            monitor_success, monitor_message = await self._monitor_usb_reboot(interface)

            if not monitor_success:
                logger.warning(f"USB reboot monitor warning: {monitor_message}")
                # Продолжаем даже если мониторинг не идеален

            # Дополнительная пауза для стабилизации
            await asyncio.sleep(5)

            # Получаем новый внешний IP
            new_external_ip = await self._get_external_ip_via_interface(interface)
            logger.info(f"External IP after USB reboot: {new_external_ip}")

            if new_external_ip:
                if new_external_ip != old_external_ip:
                    return True, f"USB reboot successful. IP changed from {old_external_ip} to {new_external_ip}"
                else:
                    return True, f"USB reboot completed. IP unchanged: {new_external_ip}"
            else:
                return False, "USB reboot completed but could not verify new IP"

        except Exception as e:
            logger.error(f"Error during USB reboot rotation: {e}")
            return False, f"USB reboot rotation error: {str(e)}"

    async def _get_modem_interface(self, device_name: str) -> Optional[str]:
        """Получение интерфейса модема из имени устройства"""
        try:
            # Для устройств типа huawei_enx0c5b8f279a64
            if 'huawei_' in device_name:
                interface_name = device_name.replace('huawei_', '')
                return interface_name

            # Если это уже интерфейс
            if device_name.startswith('enx'):
                return device_name

            return None
        except Exception as e:
            logger.error(f"Error getting modem interface: {e}")
            return None

    async def _perform_usb_reboot(self) -> Tuple[bool, str]:
        """
        Выполнение USB перезагрузки модема - ИСПРАВЛЕННАЯ ВЕРСИЯ
        """
        try:
            logger.info("Starting USB reboot...")

            # Шаг 1: Поиск USB устройства Huawei
            usb_vid = "12d1"  # Vendor ID для Huawei

            # Получаем информацию о USB устройстве
            result = await asyncio.create_subprocess_exec(
                'lsusb',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                return False, f"lsusb command failed: {stderr.decode()}"

            # Ищем Huawei устройство
            lsusb_output = stdout.decode()
            huawei_line = None
            for line in lsusb_output.split('\n'):
                if usb_vid in line and 'Huawei' in line:
                    huawei_line = line
                    break

            if not huawei_line:
                return False, "Huawei USB device not found"

            # Извлекаем bus и device
            bus_match = re.search(r'Bus (\d+) Device (\d+)', huawei_line)
            if not bus_match:
                return False, "Could not parse USB device info"

            bus = bus_match.group(1)
            device = bus_match.group(2)

            logger.info(f"Found Huawei USB device: Bus {bus} Device {device}")

            # Шаг 2: Запуск диагностики если нужно
            await self._debug_usb_device_structure(usb_vid)

            # Шаг 3: Поиск sysfs пути к устройству
            device_path = await self._find_usb_device_path(usb_vid)
            if not device_path:
                # Попробуем альтернативный метод через usbreset
                logger.warning("Could not find sysfs path, trying usbreset method...")
                return await self._usbreset_method(bus, device)

            auth_file = f"{device_path}/authorized"
            logger.info(f"Using authorization file: {auth_file}")

            # Шаг 4: Отключение USB устройства
            logger.info("Disabling USB device...")
            result = await asyncio.create_subprocess_exec(
                'sudo', 'tee', auth_file,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate(input=b'0')

            if result.returncode != 0:
                return False, f"Failed to disable USB device: {stderr.decode()}"

            # Пауза для отключения
            await asyncio.sleep(2)

            # Шаг 5: Включение USB устройства
            logger.info("Enabling USB device...")
            result = await asyncio.create_subprocess_exec(
                'sudo', 'tee', auth_file,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate(input=b'1')

            if result.returncode != 0:
                return False, f"Failed to enable USB device: {stderr.decode()}"

            logger.info("USB reboot completed successfully")
            return True, "USB reboot completed"

        except Exception as e:
            logger.error(f"Error during USB reboot: {e}")
            return False, f"USB reboot error: {str(e)}"

    async def _usbreset_method(self, bus: str, device: str) -> Tuple[bool, str]:
        """Альтернативный метод через usbreset"""
        try:
            logger.info(f"Trying usbreset method for Bus {bus} Device {device}")

            # Попробуем найти usbreset
            result = await asyncio.create_subprocess_exec(
                'which', 'usbreset',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                usbreset_path = stdout.decode().strip()
                logger.info(f"Found usbreset at: {usbreset_path}")

                # Выполняем usbreset
                result = await asyncio.create_subprocess_exec(
                    'sudo', usbreset_path, f'/dev/bus/usb/{bus.zfill(3)}/{device.zfill(3)}',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()

                if result.returncode == 0:
                    logger.info("USB reset via usbreset completed successfully")
                    return True, "USB reset completed via usbreset"
                else:
                    logger.error(f"usbreset failed: {stderr.decode()}")

            # Если usbreset не найден, пробуем через модули ядра
            logger.info("Trying kernel module reset...")

            # Перезагружаем модуль cdc_ether
            result = await asyncio.create_subprocess_exec(
                'sudo', 'modprobe', '-r', 'cdc_ether',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(2)

            result = await asyncio.create_subprocess_exec(
                'sudo', 'modprobe', 'cdc_ether',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()

            await asyncio.sleep(5)

            return True, "USB reset completed via kernel module restart"

        except Exception as e:
            logger.error(f"Error in usbreset method: {e}")
            return False, f"Alternative USB reset failed: {str(e)}"

    async def _find_usb_device_path(self, vendor_id: str) -> Optional[str]:
        """Поиск sysfs пути к USB устройству - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            logger.info(f"Searching for USB device with vendor ID: {vendor_id}")

            # Метод 1: Поиск через find команду
            result = await asyncio.create_subprocess_exec(
                'find', '/sys/bus/usb/devices/', '-name', 'idVendor',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                logger.error(f"Find command failed: {stderr.decode()}")
                return None

            # Проверяем каждый найденный файл
            for vendor_file in stdout.decode().split('\n'):
                if not vendor_file.strip():
                    continue

                try:
                    # Читаем содержимое файла
                    with open(vendor_file, 'r') as f:
                        file_vendor_id = f.read().strip()

                    if file_vendor_id == vendor_id:
                        # Возвращаем путь к директории устройства
                        device_path = vendor_file.replace('/idVendor', '')
                        auth_file = f"{device_path}/authorized"

                        logger.info(f"Found potential device path: {device_path}")

                        # Проверяем, что файл authorized существует
                        if await self._file_exists(auth_file):
                            logger.info(f"✅ Valid device path found: {device_path}")
                            return device_path
                        else:
                            logger.warning(f"Authorized file not found: {auth_file}")

                except Exception as e:
                    logger.debug(f"Error reading vendor file {vendor_file}: {e}")
                    continue

            # Метод 2: Альтернативный поиск через lsusb и /sys/bus/usb/devices
            logger.info("Trying alternative method using lsusb...")

            # Получаем Bus и Device из lsusb
            result = await asyncio.create_subprocess_exec(
                'lsusb',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                lsusb_output = stdout.decode()

                # Ищем строку с нужным vendor_id
                for line in lsusb_output.split('\n'):
                    if vendor_id in line:
                        # Парсим строку: Bus 001 Device 011: ID 12d1:1f01 Huawei Technologies Co., Ltd.
                        bus_match = re.search(r'Bus (\d+) Device (\d+)', line)
                        if bus_match:
                            bus_num = bus_match.group(1)
                            dev_num = bus_match.group(2)

                            # Формируем возможные пути
                            possible_paths = [
                                f"/sys/bus/usb/devices/{bus_num}-{dev_num}",
                                f"/sys/bus/usb/devices/{bus_num}-{dev_num}.1",
                                f"/sys/bus/usb/devices/{bus_num}-{dev_num}.2",
                                f"/sys/bus/usb/devices/usb{bus_num}",
                            ]

                            # Попробуем найти все возможные пути для этого устройства
                            for i in range(1, 20):  # Попробуем разные варианты
                                for suffix in ['', '.1', '.2', '.3', '.4']:
                                    path = f"/sys/bus/usb/devices/{bus_num}-{i}{suffix}"
                                    auth_file = f"{path}/authorized"

                                    if await self._file_exists(auth_file):
                                        # Проверяем, что это наше устройство
                                        vendor_file = f"{path}/idVendor"
                                        if await self._file_exists(vendor_file):
                                            try:
                                                with open(vendor_file, 'r') as f:
                                                    found_vendor = f.read().strip()
                                                if found_vendor == vendor_id:
                                                    logger.info(f"✅ Found device via alternative method: {path}")
                                                    return path
                                            except:
                                                continue

            # Метод 3: Прямой поиск в /sys/bus/usb/devices
            logger.info("Trying direct search in /sys/bus/usb/devices...")

            try:
                import os
                for device_name in os.listdir('/sys/bus/usb/devices'):
                    device_path = f"/sys/bus/usb/devices/{device_name}"
                    vendor_file = f"{device_path}/idVendor"
                    auth_file = f"{device_path}/authorized"

                    if os.path.exists(vendor_file) and os.path.exists(auth_file):
                        try:
                            with open(vendor_file, 'r') as f:
                                found_vendor = f.read().strip()
                            if found_vendor == vendor_id:
                                logger.info(f"✅ Found device via direct search: {device_path}")
                                return device_path
                        except:
                            continue
            except Exception as e:
                logger.error(f"Error in direct search: {e}")

            logger.error(f"Could not find sysfs path for vendor ID: {vendor_id}")
            return None

        except Exception as e:
            logger.error(f"Error finding USB device path: {e}")
            return None

    async def _file_exists(self, file_path: str) -> bool:
        """Проверка существования файла"""
        try:
            result = await asyncio.create_subprocess_exec(
                'test', '-f', file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            return result.returncode == 0
        except Exception:
            return False

    async def _monitor_usb_reboot(self, interface: str) -> Tuple[bool, str]:
        """
        Мониторинг процесса USB перезагрузки
        Отслеживает отключение и включение модема
        """
        try:
            logger.info(f"Monitoring USB reboot for interface: {interface}")

            # Находим IP модема через маршрут
            modem_ip = await self._find_modem_ip(interface)
            if not modem_ip:
                logger.warning("Could not find modem IP for monitoring")
                # Просто ждем фиксированное время
                await asyncio.sleep(5)
                return True, "Monitoring skipped - modem IP not found"

            logger.info(f"Monitoring modem IP: {modem_ip}")

            # Мониторинг отключения (15 секунд максимум)
            disconnected = False
            for i in range(15):
                try:
                    result = await asyncio.create_subprocess_exec(
                        'timeout', '2', 'ping', '-c', '1', '-W', '1', modem_ip,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await result.communicate()

                    if result.returncode != 0:
                        logger.info(f"Modem disconnected after {i + 1} seconds")
                        disconnected = True
                        break

                except Exception:
                    disconnected = True
                    break

                await asyncio.sleep(1)

            if not disconnected:
                logger.warning("Modem did not disconnect within 15 seconds")

            # Мониторинг подключения (30 секунд максимум)
            connected = False
            for i in range(30):
                try:
                    result = await asyncio.create_subprocess_exec(
                        'timeout', '2', 'ping', '-c', '1', '-W', '1', modem_ip,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await result.communicate()

                    if result.returncode == 0:
                        logger.info(f"Modem reconnected after {i + 1} seconds")
                        connected = True
                        break

                except Exception:
                    pass

                await asyncio.sleep(1)

            if not connected:
                return False, "Modem did not reconnect within 30 seconds"

            # Пауза для стабилизации соединения
            await asyncio.sleep(5)

            return True, "USB reboot monitoring completed successfully"

        except Exception as e:
            logger.error(f"Error during USB reboot monitoring: {e}")
            return False, f"Monitoring error: {str(e)}"

    async def _find_modem_ip(self, interface: str) -> Optional[str]:
        """Поиск IP модема через маршруты"""
        try:
            # Получаем маршруты для интерфейса
            result = await asyncio.create_subprocess_exec(
                'ip', 'route', 'list', 'dev', interface,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                return None

            # Ищем default gateway
            routes = stdout.decode()
            for line in routes.split('\n'):
                if 'via' in line:
                    match = re.search(r'via (\d+\.\d+\.\d+\.\d+)', line)
                    if match:
                        return match.group(1)

            return None

        except Exception as e:
            logger.error(f"Error finding modem IP: {e}")
            return None

    async def _get_external_ip_via_interface(self, interface: str) -> Optional[str]:
        """Получение внешнего IP через интерфейс"""
        try:
            # Используем curl с привязкой к интерфейсу
            result = await asyncio.create_subprocess_exec(
                'curl', '--interface', interface, '-s', '--connect-timeout', '8',
                'https://2ip.ru',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                output = stdout.decode().strip()
                # Ищем IP в выводе
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', output)
                if ip_match:
                    return ip_match.group(1)

            # Резервный способ через ifconfig.me
            result = await asyncio.create_subprocess_exec(
                'curl', '--interface', interface, '-s', '--connect-timeout', '8',
                'https://ifconfig.me',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                output = stdout.decode().strip()
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', output)
                if ip_match:
                    return ip_match.group(1)

            return None

        except Exception as e:
            logger.error(f"Error getting external IP via interface {interface}: {e}")
            return None

    # Остальные методы без изменений...
    async def _rotate_android_device(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Ротация IP для Android устройства"""
        adb_id = device.name

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

    async def _force_refresh_device_external_ip(self, device: ProxyDevice) -> Optional[str]:
        """Принудительное обновление внешнего IP устройства"""
        try:
            device_name = device.name
            device_type = device.device_type

            # Получаем внешний IP в зависимости от типа устройства
            if device_type == 'android':
                if self.device_manager:
                    android_device = await self.device_manager.get_device_by_id(device_name)
                    if android_device:
                        android_device.pop('external_ip', None)
                    return await self.device_manager.get_device_external_ip(device_name)

            elif device_type == 'usb_modem':
                if hasattr(self, 'modem_manager') and self.modem_manager:
                    return await self.modem_manager.force_refresh_external_ip(device_name)

            return await self._get_device_external_ip_by_uuid(str(device.id))

        except Exception as e:
            logger.error(f"Error force refreshing external IP for device {device.name}: {e}")
            return None

    async def _verify_ip_change(self, device: ProxyDevice, old_ip: str, max_attempts: int = 5) -> Optional[str]:
        """Улучшенная проверка изменения IP адреса устройства"""
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
                        if attempt >= 2:
                            await asyncio.sleep(8)
                        else:
                            await asyncio.sleep(3)
                else:
                    logger.warning(f"Could not get IP on attempt {attempt + 1} for device {device.name}")
                    await asyncio.sleep(3)

            except Exception as e:
                logger.warning(f"IP check attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(3)

        # Если IP не изменился, возвращаем текущий IP
        logger.info(f"IP didn't change after {max_attempts} attempts for device {device.name}")

        if old_ip and old_ip != "None":
            logger.info(f"Returning current IP {old_ip} as rotation result")
            return old_ip

        return None

    def _get_stabilization_delay(self, device_type: str) -> int:
        """Получение времени стабилизации в зависимости от типа устройства"""
        delays = {
            'android': 8,
            'usb_modem': 10,  # Увеличено для USB перезагрузки
            'raspberry_pi': 15,
            'network_device': 5
        }
        return delays.get(device_type, 10)

    async def _create_default_rotation_config(self, device: ProxyDevice) -> RotationConfig:
        """Создание конфигурации ротации по умолчанию"""
        default_methods = {
            'android': 'data_toggle',
            'usb_modem': 'usb_reboot',  # Единственный метод для USB модемов
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
                now = datetime.now()

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
                now = datetime.now()

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
                now = datetime.now()

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
        """Запуск задач ротации для всех активных устройств"""
        pass

    async def _monitor_rotation_tasks(self):
        """Мониторинг состояния задач ротации"""
        pass

    async def _get_device_external_ip_by_uuid(self, device_uuid: str) -> Optional[str]:
        """Получение внешнего IP устройства по UUID"""
        try:
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

    # Заглушки для остальных методов
    async def _rotate_raspberry_pi(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Ротация IP для Raspberry Pi"""
        return False, "Raspberry Pi rotation not implemented"

    async def _rotate_network_device(self, device: ProxyDevice, method: str) -> Tuple[bool, str]:
        """Ротация IP для сетевого устройства"""
        return False, "Network device rotation not implemented"

    async def _android_interface_reset(self, adb_id: str, device: ProxyDevice) -> Tuple[bool, str]:
        """Сброс сетевого интерфейса на Android"""
        return False, "Android interface reset not implemented"


    async def _debug_usb_device_structure(self, vendor_id: str):
        """Диагностика USB устройства для отладки"""
        try:
            logger.info(f"🔍 Debug USB device structure for vendor ID: {vendor_id}")

            # 1. Показать все USB устройства
            result = await asyncio.create_subprocess_exec(
                'lsusb',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                logger.info("📋 All USB devices:")
                for line in stdout.decode().split('\n'):
                    if line.strip():
                        logger.info(f"  {line}")

            # 2. Показать структуру /sys/bus/usb/devices
            result = await asyncio.create_subprocess_exec(
                'ls', '-la', '/sys/bus/usb/devices/',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                logger.info("📁 /sys/bus/usb/devices/ structure:")
                for line in stdout.decode().split('\n'):
                    if line.strip():
                        logger.info(f"  {line}")

            # 3. Поиск устройств с нужным vendor_id
            result = await asyncio.create_subprocess_exec(
                'find', '/sys/bus/usb/devices/', '-name', 'idVendor', '-exec', 'grep', '-l', vendor_id, '{}', ';',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                logger.info(f"🔍 Files with vendor ID {vendor_id}:")
                for line in stdout.decode().split('\n'):
                    if line.strip():
                        device_path = line.replace('/idVendor', '')
                        auth_file = f"{device_path}/authorized"
                        logger.info(f"  Device: {device_path}")
                        logger.info(f"    Authorized file: {auth_file}")
                        logger.info(f"    Exists: {await self._file_exists(auth_file)}")

            # 4. Попробуем найти по другому пути
            import os
            if os.path.exists('/sys/bus/usb/devices'):
                logger.info("🔍 Manual search in /sys/bus/usb/devices:")
                for device_name in os.listdir('/sys/bus/usb/devices'):
                    device_path = f"/sys/bus/usb/devices/{device_name}"
                    vendor_file = f"{device_path}/idVendor"

                    if os.path.exists(vendor_file):
                        try:
                            with open(vendor_file, 'r') as f:
                                found_vendor = f.read().strip()
                            if found_vendor == vendor_id:
                                auth_file = f"{device_path}/authorized"
                                logger.info(f"  ✅ Found matching device: {device_path}")
                                logger.info(f"    Authorized file: {auth_file}")
                                logger.info(f"    Exists: {os.path.exists(auth_file)}")
                        except:
                            continue

        except Exception as e:
            logger.error(f"Error in USB debug: {e}")
