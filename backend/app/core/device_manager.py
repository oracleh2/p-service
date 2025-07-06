# backend/app/core/device_manager.py - УНИВЕРСАЛЬНЫЙ МЕНЕДЖЕР УСТРОЙСТВ

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
import random

logger = structlog.get_logger()


class DeviceManager:
    """Универсальный менеджер для всех типов устройств: Android, USB модемы, Raspberry Pi"""

    def __init__(self):
        self.devices: Dict[str, dict] = {}
        self.running = False

    async def start(self):
        """Запуск менеджера устройств"""
        self.running = True
        await self.discover_all_devices()
        logger.info("Device manager started")

    async def stop(self):
        """Остановка менеджера устройств"""
        self.running = False
        logger.info("Device manager stopped")

    async def discover_all_devices(self):
        """Обнаружение всех типов устройств"""
        try:
            # Очищаем старый список
            self.devices.clear()

            # Обнаружение Android устройств
            android_devices = await self.discover_android_devices()

            # Обнаружение USB модемов
            usb_modems = await self.discover_usb_modems()

            # Обнаружение Raspberry Pi с модемами
            raspberry_devices = await self.discover_raspberry_devices()

            # Объединение всех устройств
            all_devices = {**android_devices, **usb_modems, **raspberry_devices}

            for device_id, device_info in all_devices.items():
                self.devices[device_id] = device_info
                logger.info(
                    "Discovered device",
                    device_id=device_id,
                    type=device_info['type'],
                    info=device_info.get('device_info', 'Unknown')
                )

            logger.info(f"Total devices discovered: {len(self.devices)}")

        except Exception as e:
            logger.error("Error discovering devices", error=str(e))

    async def discover_android_devices(self) -> Dict[str, dict]:
        """Обнаружение Android устройств через ADB"""
        devices = {}

        try:
            logger.info("Scanning for Android devices via ADB...")

            result = await asyncio.create_subprocess_exec(
                'adb', 'devices', '-l',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                logger.error(f"ADB command failed: {stderr.decode()}")
                return devices

            devices_output = stdout.decode().strip()
            lines = devices_output.split('\n')[1:]  # Пропускаем заголовок

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Парсинг строки ADB
                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]

                    if status == 'device':
                        logger.info(f"Found Android device: {device_id}")

                        # Получаем детальную информацию
                        device_details = await self.get_android_device_details(device_id)

                        android_device_id = f"android_{device_id}"
                        devices[android_device_id] = {
                            'id': android_device_id,
                            'type': 'android',
                            'interface': device_id,
                            'adb_id': device_id,
                            'device_info': device_details.get('friendly_name', f"Android device {device_id}"),
                            'status': 'online',
                            'manufacturer': device_details.get('manufacturer', 'Unknown'),
                            'model': device_details.get('model', 'Unknown'),
                            'android_version': device_details.get('android_version', 'Unknown'),
                            'battery_level': device_details.get('battery_level', 0),
                            'rotation_methods': ['data_toggle', 'airplane_mode'],
                            'last_seen': datetime.now().isoformat()
                        }

        except FileNotFoundError:
            logger.error("ADB not found - install android-tools-adb")
        except Exception as e:
            logger.error("Error discovering Android devices", error=str(e))

        return devices

    async def discover_usb_modems(self) -> Dict[str, dict]:
        """Обнаружение USB 4G модемов"""
        modems = {}

        try:
            logger.info("Scanning for USB modems...")

            # Проверяем стандартные serial порты для USB модемов
            for device_path in ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyUSB2',
                                '/dev/ttyACM0', '/dev/ttyACM1', '/dev/ttyACM2']:
                try:
                    # Попытка открыть порт
                    with serial.Serial(device_path, timeout=1) as ser:
                        modem_id = f"usb_{device_path.split('/')[-1]}"

                        # Получаем информацию о модеме через AT команды
                        modem_info = await self.get_usb_modem_details(device_path)

                        modems[modem_id] = {
                            'id': modem_id,
                            'type': 'usb_modem',
                            'interface': device_path,
                            'device_info': f"USB modem on {device_path}",
                            'status': 'online',
                            'operator': modem_info.get('operator', 'Unknown'),
                            'signal_strength': modem_info.get('signal_strength', 'N/A'),
                            'technology': modem_info.get('technology', 'Unknown'),
                            'rotation_methods': ['at_commands', 'network_reset'],
                            'last_seen': datetime.now().isoformat()
                        }
                        logger.info(f"Found USB modem on {device_path}")

                except (serial.SerialException, PermissionError):
                    continue

        except Exception as e:
            logger.error("Error discovering USB modems", error=str(e))

        return modems

    async def discover_raspberry_devices(self) -> Dict[str, dict]:
        """Обнаружение Raspberry Pi с 4G модулями"""
        devices = {}

        try:
            logger.info("Scanning for Raspberry Pi devices...")

            # Поиск PPP и WWAN интерфейсов
            interfaces = netifaces.interfaces()

            for interface in interfaces:
                if interface.startswith('ppp') or interface.startswith('wwan'):
                    device_id = f"raspberry_{interface}"

                    devices[device_id] = {
                        'id': device_id,
                        'type': 'raspberry_pi',
                        'interface': interface,
                        'device_info': f"Raspberry Pi with modem on {interface}",
                        'status': 'online',
                        'rotation_methods': ['ppp_reset', 'modem_restart'],
                        'last_seen': datetime.now().isoformat()
                    }
                    logger.info(f"Found Raspberry Pi device on {interface}")

        except Exception as e:
            logger.error("Error discovering Raspberry Pi devices", error=str(e))

        return devices

    async def get_android_device_details(self, device_id: str) -> Dict[str, any]:
        """Получение детальной информации об Android устройстве"""
        details = {}

        try:
            commands = {
                'manufacturer': ['getprop', 'ro.product.manufacturer'],
                'model': ['getprop', 'ro.product.model'],
                'android_version': ['getprop', 'ro.build.version.release'],
                'brand': ['getprop', 'ro.product.brand'],
            }

            for key, cmd in commands.items():
                try:
                    result = await asyncio.create_subprocess_exec(
                        'adb', '-s', device_id, 'shell', *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, _ = await result.communicate()

                    if result.returncode == 0:
                        details[key] = stdout.decode().strip()

                except Exception:
                    details[key] = 'Unknown'

            # Получение уровня батареи
            try:
                result = await asyncio.create_subprocess_exec(
                    'adb', '-s', device_id, 'shell', 'dumpsys', 'battery',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await result.communicate()

                if result.returncode == 0:
                    battery_output = stdout.decode()
                    level_match = re.search(r'level:\s*(\d+)', battery_output)
                    if level_match:
                        details['battery_level'] = int(level_match.group(1))

            except Exception:
                details['battery_level'] = 0

            # Создаем friendly name
            manufacturer = details.get('manufacturer', 'Unknown')
            model = details.get('model', 'Unknown')
            details['friendly_name'] = f"{manufacturer} {model}".strip()

        except Exception as e:
            logger.error(f"Error getting Android device details: {e}")

        return details

    async def get_usb_modem_details(self, device_path: str) -> Dict[str, any]:
        """Получение информации о USB модеме через AT команды"""
        details = {}

        try:
            with serial.Serial(device_path, 115200, timeout=5) as ser:
                commands = {
                    'manufacturer': 'AT+CGMI',
                    'model': 'AT+CGMM',
                    'signal_strength': 'AT+CSQ',
                    'operator': 'AT+COPS?',
                    'technology': 'AT+CREG?'
                }

                for key, cmd in commands.items():
                    try:
                        ser.write(f'{cmd}\r\n'.encode())
                        time.sleep(0.5)
                        response = ser.read_all().decode('utf-8', errors='ignore')

                        # Простой парсинг ответа
                        if 'OK' in response:
                            lines = response.split('\n')
                            for line in lines:
                                if line.strip() and not line.startswith('AT') and 'OK' not in line:
                                    details[key] = line.strip()
                                    break
                        else:
                            details[key] = 'Unknown'

                    except Exception:
                        details[key] = 'Unknown'

        except Exception as e:
            logger.error(f"Error getting USB modem details: {e}")

        return details

    async def get_all_devices(self) -> Dict[str, dict]:
        """Получение всех устройств"""
        return self.devices.copy()

    async def get_device_by_id(self, device_id: str) -> Optional[dict]:
        """Получение устройства по ID"""
        return self.devices.get(device_id)

    async def get_available_devices(self) -> List[dict]:
        """Получение доступных (онлайн) устройств"""
        return [device for device in self.devices.values() if device.get('status') == 'online']

    async def get_random_device(self) -> Optional[dict]:
        """Получение случайного доступного устройства"""
        available = await self.get_available_devices()
        return random.choice(available) if available else None

    async def get_device_by_operator(self, operator: str) -> Optional[dict]:
        """Получение устройства по оператору"""
        for device in self.devices.values():
            if device.get('operator', '').lower() == operator.lower() and device.get('status') == 'online':
                return device
        return None

    async def get_device_by_region(self, region: str) -> Optional[dict]:
        """Получение устройства по региону"""
        for device in self.devices.values():
            if device.get('region', '').lower() == region.lower() and device.get('status') == 'online':
                return device
        return None

    async def is_device_online(self, device_id: str) -> bool:
        """Проверка онлайн статуса устройства"""
        device = self.devices.get(device_id)
        return device is not None and device.get('status') == 'online'

    async def get_device_external_ip(self, device_id: str) -> Optional[str]:
        """Получение внешнего IP устройства"""
        device = self.devices.get(device_id)
        if not device:
            return None

        device_type = device.get('type')

        if device_type == 'android':
            return await self.get_android_external_ip(device)
        elif device_type == 'usb_modem':
            return await self.get_usb_modem_external_ip(device)
        elif device_type == 'raspberry_pi':
            return await self.get_raspberry_external_ip(device)

        return None

    async def get_android_external_ip(self, device: dict) -> Optional[str]:
        """Получение внешнего IP Android устройства"""
        try:
            device_id = device['adb_id']

            # Попытка получить IP через ADB
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'ip', 'route', 'get', '8.8.8.8',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()

            if result.returncode == 0:
                output = stdout.decode()
                ip_match = re.search(r'src (\d+\.\d+\.\d+\.\d+)', output)
                if ip_match:
                    return ip_match.group(1)

        except Exception as e:
            logger.error(f"Error getting Android external IP: {e}")

        return None

    async def get_usb_modem_external_ip(self, device: dict) -> Optional[str]:
        """Получение внешнего IP USB модема"""
        try:
            # Можно использовать AT команды или проверку сетевых интерфейсов
            # Пока возвращаем None, можно дополнить позже
            return None
        except Exception as e:
            logger.error(f"Error getting USB modem external IP: {e}")
            return None

    async def get_raspberry_external_ip(self, device: dict) -> Optional[str]:
        """Получение внешнего IP Raspberry Pi"""
        try:
            interface = device['interface']
            addrs = netifaces.ifaddresses(interface)

            if netifaces.AF_INET in addrs:
                return addrs[netifaces.AF_INET][0]['addr']

        except Exception as e:
            logger.error(f"Error getting Raspberry Pi external IP: {e}")

        return None

    async def rotate_device_ip(self, device_id: str) -> bool:
        """Ротация IP устройства"""
        device = self.devices.get(device_id)
        if not device:
            return False

        device_type = device.get('type')

        if device_type == 'android':
            return await self.rotate_android_ip(device)
        elif device_type == 'usb_modem':
            return await self.rotate_usb_modem_ip(device)
        elif device_type == 'raspberry_pi':
            return await self.rotate_raspberry_ip(device)

        return False

    async def rotate_android_ip(self, device: dict) -> bool:
        """Ротация IP для Android устройства"""
        try:
            device_id = device['adb_id']
            logger.info(f"Starting Android IP rotation for {device_id}")

            # Отключение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'svc', 'data', 'disable'
            )
            await result.wait()

            # Ждем немного
            await asyncio.sleep(3)

            # Включение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'svc', 'data', 'enable'
            )
            await result.wait()

            # Ждем восстановления соединения
            await asyncio.sleep(10)

            logger.info(f"Android IP rotation completed for {device_id}")
            return True

        except Exception as e:
            logger.error(f"Error rotating Android IP: {e}")
            return False

    async def rotate_usb_modem_ip(self, device: dict) -> bool:
        """Ротация IP для USB модема"""
        try:
            interface = device['interface']
            logger.info(f"Starting USB modem IP rotation for {interface}")

            with serial.Serial(interface, 115200, timeout=5) as ser:
                # Отключение модема
                ser.write(b'AT+CFUN=0\r\n')
                time.sleep(2)

                # Включение модема
                ser.write(b'AT+CFUN=1\r\n')
                time.sleep(10)

            logger.info(f"USB modem IP rotation completed for {interface}")
            return True

        except Exception as e:
            logger.error(f"Error rotating USB modem IP: {e}")
            return False

    async def rotate_raspberry_ip(self, device: dict) -> bool:
        """Ротация IP для Raspberry Pi"""
        try:
            interface = device['interface']
            logger.info(f"Starting Raspberry Pi IP rotation for {interface}")

            # Перезапуск PPP соединения
            if interface.startswith('ppp'):
                # Отключение PPP
                result = await asyncio.create_subprocess_exec('sudo', 'poff', interface)
                await result.wait()

                await asyncio.sleep(3)

                # Включение PPP
                result = await asyncio.create_subprocess_exec('sudo', 'pon', interface)
                await result.wait()

                await asyncio.sleep(10)

            logger.info(f"Raspberry Pi IP rotation completed for {interface}")
            return True

        except Exception as e:
            logger.error(f"Error rotating Raspberry Pi IP: {e}")
            return False

    async def get_summary(self) -> Dict[str, any]:
        """Получение сводной информации об устройствах"""
        total = len(self.devices)
        online = len([d for d in self.devices.values() if d.get('status') == 'online'])

        by_type = {}
        for device in self.devices.values():
            device_type = device.get('type', 'unknown')
            by_type[device_type] = by_type.get(device_type, 0) + 1

        return {
            'total_devices': total,
            'online_devices': online,
            'offline_devices': total - online,
            'devices_by_type': by_type,
            'last_discovery': datetime.now().isoformat()
        }
