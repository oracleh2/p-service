# backend/app/core/modem_manager.py
import asyncio
import serial
import subprocess
import time
import re
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import structlog
import psutil
import netifaces

logger = structlog.get_logger()


class ModemManager:
    """Менеджер для прямого управления модемами без агентов"""

    def __init__(self):
        self.modems: Dict[str, dict] = {}
        self.running = False

    async def start(self):
        """Запуск менеджера модемов"""
        self.running = True

        # Автоматическое обнаружение модемов
        await self.discover_modems()

        logger.info("Modem manager started")

    async def stop(self):
        """Остановка менеджера модемов"""
        self.running = False
        logger.info("Modem manager stopped")

    async def discover_modems(self):
        """Автоматическое обнаружение подключенных модемов"""
        try:
            # Обнаружение USB модемов
            usb_modems = await self.discover_usb_modems()

            # Обнаружение Android устройств
            android_devices = await self.discover_android_devices()

            # Обнаружение сетевых модемов (Raspberry Pi)
            network_modems = await self.discover_network_modems()

            # Объединение всех найденных модемов
            all_modems = {**usb_modems, **android_devices, **network_modems}

            for modem_id, modem_info in all_modems.items():
                self.modems[modem_id] = modem_info
                logger.info(
                    "Discovered modem",
                    modem_id=modem_id,
                    type=modem_info['type'],
                    info=modem_info.get('device_info', 'Unknown')
                )

        except Exception as e:
            logger.error("Error discovering modems", error=str(e))

    async def discover_usb_modems(self) -> Dict[str, dict]:
        """Обнаружение USB модемов"""
        modems = {}

        try:
            # Поиск USB serial портов
            for device in ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyUSB2', '/dev/ttyACM0', '/dev/ttyACM1']:
                try:
                    # Попытка открыть порт для проверки
                    with serial.Serial(device, timeout=1) as ser:
                        modem_id = f"usb_{device.split('/')[-1]}"
                        modems[modem_id] = {
                            'id': modem_id,
                            'type': 'usb_modem',
                            'interface': device,
                            'device_info': f"USB modem on {device}",
                            'status': 'detected'
                        }
                        logger.info(f"Found USB modem on {device}")

                except (serial.SerialException, PermissionError):
                    continue

        except Exception as e:
            logger.error("Error discovering USB modems", error=str(e))

        return modems

    async def discover_android_devices(self) -> Dict[str, dict]:
        """Обнаружение Android устройств через ADB - ИСПРАВЛЕННАЯ РЕАЛИЗАЦИЯ"""
        modems = {}

        try:
            logger.info("Scanning for Android devices via ADB...")

            # Проверка доступности ADB
            result = await asyncio.create_subprocess_exec(
                'adb', 'devices', '-l',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            logger.info(f"ADB command return code: {result.returncode}")
            logger.info(f"ADB stdout: {stdout.decode()}")
            logger.info(f"ADB stderr: {stderr.decode()}")

            if result.returncode != 0:
                logger.error(f"ADB command failed with code {result.returncode}: {stderr.decode()}")
                return modems

            devices_output = stdout.decode().strip()
            logger.info(f"ADB devices output: '{devices_output}'")

            lines = devices_output.split('\n')
            logger.info(f"Split into {len(lines)} lines: {lines}")

            # Пропускаем заголовок "List of devices attached"
            device_lines = lines[1:]

            for i, line in enumerate(device_lines):
                line = line.strip()
                logger.info(f"Processing line {i}: '{line}' (length: {len(line)})")

                if not line:
                    logger.info(f"Line {i} is empty, skipping")
                    continue

                # ИСПРАВЛЕННЫЙ ПАРСИНГ: используем регулярное выражение или разбиение по пробелам
                # Формат: "AH3SCP4B11207250       device usb:1-1.2 product:JDY-LX1 model:JDY_LX1 device:HNJDY-M1 transport_id:1"

                # Вариант 1: Простое разбиение по пробелам
                parts = line.split()
                logger.info(f"Line {i} split into {len(parts)} parts: {parts}")

                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]

                    logger.info(f"Found Android device: {device_id}, status: {status}")

                    if status == 'device':  # Только полностью подключенные устройства
                        logger.info(f"Device {device_id} is fully connected, getting details...")

                        # Получаем детальную информацию об устройстве
                        device_details = await self.get_android_device_details(device_id)
                        logger.info(f"Device details for {device_id}: {device_details}")

                        modem_id = f"android_{device_id}"
                        modems[modem_id] = {
                            'id': modem_id,
                            'type': 'android',
                            'interface': device_id,
                            'adb_id': device_id,
                            'device_info': device_details.get('friendly_name', f"Android device {device_id}"),
                            'status': 'online',
                            'manufacturer': device_details.get('manufacturer', 'Unknown'),
                            'model': device_details.get('model', 'Unknown'),
                            'android_version': device_details.get('android_version', 'Unknown'),
                            'battery_level': device_details.get('battery_level', 0),
                            'usb_tethering': device_details.get('usb_tethering', False),
                            'rotation_methods': ['data_toggle', 'airplane_mode'],
                            'last_seen': datetime.now().isoformat()
                        }

                        logger.info(
                            "Android device discovered successfully",
                            device_id=device_id,
                            modem_id=modem_id,
                            manufacturer=device_details.get('manufacturer'),
                            model=device_details.get('model'),
                            battery=device_details.get('battery_level')
                        )
                    else:
                        logger.warning(f"Device {device_id} has status '{status}', not 'device'")
                else:
                    logger.warning(f"Line {i} doesn't have enough parts: {parts}")

            logger.info(f"Total Android devices found: {len(modems)}")

        except FileNotFoundError:
            logger.error("ADB not found - install android-tools-adb")
        except Exception as e:
            logger.error("Error discovering Android devices", error=str(e))
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

        return modems

    # АЛЬТЕРНАТИВНЫЙ БОЛЕЕ ПРОДВИНУТЫЙ ПАРСЕР
    async def discover_android_devices_advanced(self) -> Dict[str, dict]:
        """Обнаружение Android устройств через ADB - ПРОДВИНУТАЯ РЕАЛИЗАЦИЯ"""
        modems = {}

        try:
            logger.info("Scanning for Android devices via ADB...")

            # Проверка доступности ADB
            result = await asyncio.create_subprocess_exec(
                'adb', 'devices', '-l',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                logger.error(f"ADB command failed with code {result.returncode}: {stderr.decode()}")
                return modems

            devices_output = stdout.decode().strip()
            lines = devices_output.split('\n')

            # Пропускаем заголовок "List of devices attached"
            device_lines = lines[1:]

            import re

            for i, line in enumerate(device_lines):
                line = line.strip()

                if not line:
                    continue

                # Используем регулярное выражение для более точного парсинга
                # Паттерн: device_id + пробелы + status + остальная информация
                match = re.match(r'^(\w+)\s+(device|offline|unauthorized)\s*(.*)', line)

                if match:
                    device_id = match.group(1)
                    status = match.group(2)
                    extra_info = match.group(3)

                    logger.info(f"Parsed device: {device_id}, status: {status}, extra: {extra_info}")

                    if status == 'device':
                        # Парсим дополнительную информацию из extra_info
                        device_info = {}

                        # Извлекаем модель из строки типа "product:JDY-LX1 model:JDY_LX1"
                        model_match = re.search(r'model:(\S+)', extra_info)
                        if model_match:
                            device_info['model_from_adb'] = model_match.group(1)

                        product_match = re.search(r'product:(\S+)', extra_info)
                        if product_match:
                            device_info['product_from_adb'] = product_match.group(1)

                        # Получаем детальную информацию об устройстве
                        device_details = await self.get_android_device_details(device_id)
                        device_details.update(device_info)

                        modem_id = f"android_{device_id}"
                        modems[modem_id] = {
                            'id': modem_id,
                            'type': 'android',
                            'interface': device_id,
                            'adb_id': device_id,
                            'device_info': device_details.get('friendly_name',
                                                              f"Android {device_details.get('model', device_id)}"),
                            'status': 'online',
                            'manufacturer': device_details.get('manufacturer', 'Unknown'),
                            'model': device_details.get('model', device_details.get('model_from_adb', 'Unknown')),
                            'android_version': device_details.get('android_version', 'Unknown'),
                            'battery_level': device_details.get('battery_level', 0),
                            'usb_tethering': device_details.get('usb_tethering', False),
                            'rotation_methods': ['data_toggle', 'airplane_mode'],
                            'last_seen': datetime.now().isoformat()
                        }

                        logger.info(
                            f"Android device discovered: {device_id} ({device_details.get('model', 'Unknown')})")

                    elif status == 'unauthorized':
                        logger.warning(
                            f"Device {device_id} is unauthorized - enable USB debugging and accept the prompt")
                    elif status == 'offline':
                        logger.warning(f"Device {device_id} is offline")
                else:
                    logger.warning(f"Could not parse line: '{line}'")

            logger.info(f"Total Android devices found: {len(modems)}")

        except FileNotFoundError:
            logger.error("ADB not found - install android-tools-adb")
        except Exception as e:
            logger.error("Error discovering Android devices", error=str(e))
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

        return modems

    async def get_android_device_details(self, device_id: str) -> Dict[str, any]:
        """Получение детальной информации об Android устройстве"""
        details = {}

        try:
            # Команды для получения информации об устройстве
            commands = {
                'manufacturer': ['getprop', 'ro.product.manufacturer'],
                'model': ['getprop', 'ro.product.model'],
                'android_version': ['getprop', 'ro.build.version.release'],
                'brand': ['getprop', 'ro.product.brand'],
                'device': ['getprop', 'ro.product.device'],
                'sdk_version': ['getprop', 'ro.build.version.sdk'],
            }

            # Выполняем команды для получения информации
            for key, command in commands.items():
                try:
                    result = await asyncio.create_subprocess_exec(
                        'adb', '-s', device_id, 'shell', *command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, _ = await result.communicate()

                    if result.returncode == 0:
                        value = stdout.decode().strip()
                        if value and value != 'unknown':
                            details[key] = value
                        else:
                            details[key] = "Unknown"
                    else:
                        details[key] = "Unknown"

                except Exception as e:
                    logger.warning(f"Failed to get {key} for {device_id}: {e}")
                    details[key] = "Unknown"

            # Получаем информацию о батарее
            try:
                result = await asyncio.create_subprocess_exec(
                    'adb', '-s', device_id, 'shell', 'dumpsys', 'battery',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await result.communicate()

                if result.returncode == 0:
                    battery_output = stdout.decode()
                    # Парсим уровень батареи
                    battery_match = re.search(r'level: (\d+)', battery_output)
                    if battery_match:
                        details['battery_level'] = int(battery_match.group(1))
                    else:
                        details['battery_level'] = 0
                else:
                    details['battery_level'] = 0

            except Exception as e:
                logger.warning(f"Failed to get battery info for {device_id}: {e}")
                details['battery_level'] = 0

            # Проверяем статус USB tethering (не обязательно для работы)
            try:
                result = await asyncio.create_subprocess_exec(
                    'adb', '-s', device_id, 'shell', 'dumpsys', 'connectivity',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await result.communicate()

                if result.returncode == 0:
                    connectivity_output = stdout.decode()
                    # Ищем USB tethering статус
                    details['usb_tethering'] = 'USB tethering' in connectivity_output
                else:
                    details['usb_tethering'] = False

            except Exception as e:
                logger.warning(f"Failed to get USB tethering status for {device_id}: {e}")
                details['usb_tethering'] = False

            # Создаем friendly name
            manufacturer = details.get('manufacturer', 'Unknown')
            model = details.get('model', 'Unknown')
            details['friendly_name'] = f"{manufacturer} {model}".strip()

        except Exception as e:
            logger.error(f"Error getting Android device details for {device_id}: {e}")

        return details

    async def check_android_tethering(self, device_id: str) -> bool:
        """Проверка поддержки USB tethering"""
        try:
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'which', 'svc',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()

            # Если команда svc доступна, значит устройство поддерживает управление данными
            return result.returncode == 0 and stdout.decode().strip()

        except Exception:
            return False

    async def discover_network_modems(self) -> Dict[str, dict]:
        """Обнаружение сетевых модемов (Raspberry Pi и др.)"""
        modems = {}

        try:
            # Поиск PPP интерфейсов (обычно используются с модемами)
            interfaces = netifaces.interfaces()

            for interface in interfaces:
                if interface.startswith('ppp') or interface.startswith('wwan'):
                    modem_id = f"network_{interface}"
                    modems[modem_id] = {
                        'id': modem_id,
                        'type': 'network_modem',
                        'interface': interface,
                        'device_info': f"Network modem on {interface}",
                        'status': 'detected'
                    }

        except Exception as e:
            logger.error("Error discovering network modems", error=str(e))

        return modems

    async def rotate_usb_modem(self, modem: dict) -> bool:
        """Ротация IP для USB модема"""
        try:
            interface = modem['interface']

            logger.info("Starting USB modem rotation", modem_id=modem['id'])

            # Простая ротация через AT команды
            with serial.Serial(interface, 115200, timeout=5) as ser:
                # Отключение модема
                ser.write(b'AT+CFUN=0\r\n')
                time.sleep(2)

                # Включение модема
                ser.write(b'AT+CFUN=1\r\n')
                time.sleep(10)

            logger.info("USB modem rotation completed", modem_id=modem['id'])
            return True

        except Exception as e:
            logger.error("Error in USB modem rotation", modem_id=modem['id'], error=str(e))
            return False

    async def rotate_android_modem(self, modem: dict) -> bool:
        """Ротация IP для Android устройства через ADB - РЕАЛЬНАЯ РЕАЛИЗАЦИЯ"""
        try:
            device_id = modem['adb_id']

            logger.info("Starting Android modem rotation", modem_id=modem['id'], device_id=device_id)

            # Отключение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'svc', 'data', 'disable',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.wait()

            if result.returncode != 0:
                logger.error("Failed to disable mobile data", device_id=device_id)
                return False

            logger.info("Mobile data disabled, waiting...", device_id=device_id)

            # Ожидание
            await asyncio.sleep(3)

            # Включение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'svc', 'data', 'enable',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.wait()

            if result.returncode != 0:
                logger.error("Failed to enable mobile data", device_id=device_id)
                return False

            logger.info("Mobile data enabled, waiting for connection...", device_id=device_id)

            # Ожидание подключения
            await asyncio.sleep(10)

            logger.info("Android modem rotation completed", modem_id=modem['id'])
            return True

        except Exception as e:
            logger.error("Error in Android modem rotation", modem_id=modem['id'], error=str(e))
            return False

    async def rotate_network_modem(self, modem: dict) -> bool:
        """Ротация IP для сетевого модема"""
        try:
            interface = modem['interface']

            logger.info("Starting network modem rotation", modem_id=modem['id'])

            # Отключение интерфейса
            result = await asyncio.create_subprocess_exec(
                'sudo', 'ifdown', interface
            )
            await result.wait()

            # Ожидание
            await asyncio.sleep(5)

            # Включение интерфейса
            result = await asyncio.create_subprocess_exec(
                'sudo', 'ifup', interface
            )
            await result.wait()

            # Ожидание подключения
            await asyncio.sleep(15)

            logger.info("Network modem rotation completed", modem_id=modem['id'])
            return True

        except Exception as e:
            logger.error("Error in network modem rotation", modem_id=modem['id'], error=str(e))
            return False

    async def get_modem_external_ip(self, modem_id: str) -> Optional[str]:
        """Получение внешнего IP модема"""
        if modem_id not in self.modems:
            return None

        modem = self.modems[modem_id]

        try:
            if modem['type'] == 'usb_modem':
                return await self.get_usb_modem_ip(modem)
            elif modem['type'] == 'android':
                return await self.get_android_modem_ip(modem)
            elif modem['type'] == 'network_modem':
                return await self.get_network_modem_ip(modem)

        except Exception as e:
            logger.error("Error getting modem IP", modem_id=modem_id, error=str(e))

        return None

    async def get_usb_modem_ip(self, modem: dict) -> Optional[str]:
        """Получение IP USB модема"""
        try:
            # Поиск PPP интерфейса
            interfaces = netifaces.interfaces()

            for interface in interfaces:
                if interface.startswith('ppp'):
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        return addrs[netifaces.AF_INET][0]['addr']

        except Exception as e:
            logger.error("Error getting USB modem IP", error=str(e))

        return None

    async def get_android_modem_ip(self, modem: dict) -> Optional[str]:
        """Получение IP Android устройства - РЕАЛЬНАЯ РЕАЛИЗАЦИЯ"""
        try:
            device_id = modem['adb_id']

            # Получение IP через ADB
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'ip', 'route', 'get', '8.8.8.8',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                # Парсинг IP из вывода
                output = stdout.decode()
                ip_match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', output)

                if ip_match:
                    return ip_match.group(1)

        except Exception as e:
            logger.error("Error getting Android modem IP", error=str(e))

        return None

    async def get_network_modem_ip(self, modem: dict) -> Optional[str]:
        """Получение IP сетевого модема"""
        try:
            interface = modem['interface']
            addrs = netifaces.ifaddresses(interface)

            if netifaces.AF_INET in addrs:
                return addrs[netifaces.AF_INET][0]['addr']

        except Exception as e:
            logger.error("Error getting network modem IP", error=str(e))

        return None

    async def get_usb_modem_details(self, modem: dict) -> dict:
        """Получение детальной информации о USB модеме"""
        try:
            interface = modem['interface']
            details = {
                'signal_strength': 'N/A',
                'operator': 'Unknown',
                'technology': 'Unknown',
                'temperature': 'N/A'
            }

            with serial.Serial(interface, 115200, timeout=5) as ser:
                commands = {
                    'signal_strength': 'AT+CSQ',
                    'operator': 'AT+COPS?',
                    'technology': 'AT+CREG?'
                }

                for key, command in commands.items():
                    try:
                        ser.write(f'{command}\r\n'.encode())
                        response = ser.read(200).decode()
                        details[key] = response.strip()
                    except:
                        details[key] = "N/A"

                ser.close()
                return details

        except Exception as e:
            logger.error("Error getting USB modem details", error=str(e))
            return {}

    async def get_android_modem_details(self, modem: dict) -> dict:
        """Получение детальной информации об Android устройстве"""
        try:
            device_id = modem['adb_id']
            details = {}

            # Получение информации об устройстве
            commands = {
                'manufacturer': 'getprop ro.product.manufacturer',
                'model': 'getprop ro.product.model',
                'android_version': 'getprop ro.build.version.release',
                'battery_level': 'dumpsys battery | grep level'
            }

            for key, command in commands.items():
                try:
                    result = await asyncio.create_subprocess_exec(
                        'adb', '-s', device_id, 'shell', command,
                        stdout=asyncio.subprocess.PIPE
                    )
                    stdout, _ = await result.communicate()
                    details[key] = stdout.decode().strip()
                except:
                    details[key] = "N/A"

            return details

        except Exception as e:
            logger.error("Error getting Android modem details", error=str(e))
            return {}

    async def get_all_modems(self) -> Dict[str, dict]:
        """Получение информации о всех модемах"""
        return self.modems.copy()

    async def is_modem_online(self, modem_id: str) -> bool:
        """Проверка, что модем онлайн"""
        if modem_id not in self.modems:
            return False

        # Простая проверка - есть ли IP адрес
        ip = await self.get_modem_external_ip(modem_id)
        return ip is not None
