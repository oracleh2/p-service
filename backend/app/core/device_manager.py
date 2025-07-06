# backend/app/core/device_manager.py - ENHANCED VERSION WITH USB INTERFACE DETECTION

import asyncio
import serial
import subprocess
import time
import re
import json
import netifaces
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import structlog
import psutil
import random

logger = structlog.get_logger()


class DeviceManager:
    """Улучшенный менеджер устройств с поддержкой USB интерфейсов"""

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
        """Обнаружение всех типов устройств с улучшенной логикой"""
        try:
            # Очищаем старый список
            self.devices.clear()

            logger.info("Starting comprehensive device discovery...")

            # 1. Обнаружение Android устройств с USB интерфейсами
            android_devices = await self.discover_android_devices_with_interfaces()

            # 2. Обнаружение USB модемов
            usb_modems = await self.discover_usb_modems()

            # 3. Обнаружение Raspberry Pi с модемами
            raspberry_devices = await self.discover_raspberry_devices()

            # Объединение всех устройств
            all_devices = {**android_devices, **usb_modems, **raspberry_devices}

            for device_id, device_info in all_devices.items():
                self.devices[device_id] = device_info
                logger.info(
                    "Device discovered",
                    device_id=device_id,
                    type=device_info['type'],
                    interface=device_info.get('usb_interface', device_info.get('interface', 'N/A')),
                    info=device_info.get('device_info', 'Unknown')
                )

            logger.info(f"✅ Total devices discovered: {len(self.devices)}")

        except Exception as e:
            logger.error("Error discovering devices", error=str(e))

    async def discover_android_devices_with_interfaces(self) -> Dict[str, dict]:
        """Обнаружение Android устройств с обнаружением USB интерфейсов"""
        devices = {}

        try:
            logger.info("Scanning for Android devices with USB interfaces...")

            # Получаем список Android устройств через ADB
            adb_devices = await self.get_adb_devices()

            # Получаем список USB tethering интерфейсов
            usb_interfaces = await self.detect_usb_tethering_interfaces()

            logger.info(f"Found {len(adb_devices)} ADB devices and {len(usb_interfaces)} USB interfaces")

            # Сопоставляем Android устройства с USB интерфейсами
            for adb_device in adb_devices:
                device_id = adb_device['device_id']
                device_details = await self.get_android_device_details(device_id)

                # Пытаемся найти соответствующий USB интерфейс
                matched_interface = await self.match_android_to_usb_interface(
                    device_id, device_details, usb_interfaces
                )

                android_device_id = f"android_{device_id}"
                device_info = {
                    'id': android_device_id,
                    'type': 'android',
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

                # Добавляем информацию об USB интерфейсе если найден
                if matched_interface:
                    device_info.update({
                        'usb_interface': matched_interface['interface'],
                        'usb_ip': matched_interface['ip'],
                        'usb_status': matched_interface['status'],
                        'routing_capable': True,
                        'interface_type': 'usb_tethering'
                    })
                    logger.info(
                        f"✅ Android device {device_id} matched with USB interface {matched_interface['interface']}")
                else:
                    device_info.update({
                        'usb_interface': None,
                        'usb_ip': None,
                        'routing_capable': False,
                        'interface_type': 'adb_only'
                    })
                    logger.warning(f"⚠️  Android device {device_id} has no USB interface")

                devices[android_device_id] = device_info

        except Exception as e:
            logger.error("Error discovering Android devices with interfaces", error=str(e))

        return devices

    async def get_adb_devices(self) -> List[Dict[str, str]]:
        """Получение списка Android устройств через ADB"""
        devices = []

        try:
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

                # Парсинг с помощью регулярного выражения
                match = re.match(r'^(\w+)\s+(device|offline|unauthorized)\s*(.*)', line)
                if match:
                    device_id = match.group(1)
                    status = match.group(2)
                    extra_info = match.group(3)

                    if status == 'device':
                        devices.append({
                            'device_id': device_id,
                            'status': status,
                            'extra_info': extra_info
                        })

        except FileNotFoundError:
            logger.error("ADB not found - install android-tools-adb")
        except Exception as e:
            logger.error("Error getting ADB devices", error=str(e))

        return devices

    async def detect_usb_tethering_interfaces(self) -> List[Dict[str, str]]:
        """Обнаружение USB tethering интерфейсов"""
        interfaces = []

        try:
            # Список возможных USB tethering интерфейсов
            potential_interfaces = [
                'enx566cf3eaaf4b',  # HONOR USB interface
                'usb0', 'usb1', 'usb2',
                'rndis0', 'rndis1', 'rndis2',
                'enp0s20u1', 'enp0s20u2',
                'enp5s0f7u1', 'enp5s0f7u2',
            ]

            # Также ищем интерфейсы по паттерну
            all_interfaces = netifaces.interfaces()
            for interface in all_interfaces:
                if (interface.startswith('enx') or
                    interface.startswith('usb') or
                    interface.startswith('rndis')):
                    if interface not in potential_interfaces:
                        potential_interfaces.append(interface)

            logger.info(f"Checking {len(potential_interfaces)} potential USB interfaces...")

            for interface in potential_interfaces:
                if interface in all_interfaces:
                    interface_info = await self.get_interface_info(interface)
                    if interface_info:
                        interfaces.append(interface_info)
                        logger.info(f"Found USB interface: {interface} ({interface_info['ip']})")

        except Exception as e:
            logger.error("Error detecting USB tethering interfaces", error=str(e))

        return interfaces

    async def get_interface_info(self, interface: str) -> Optional[Dict[str, str]]:
        """Получение информации об интерфейсе"""
        try:
            if interface not in netifaces.interfaces():
                return None

            addrs = netifaces.ifaddresses(interface)

            # Проверяем наличие IPv4 адреса
            if netifaces.AF_INET not in addrs:
                return None

            ip_info = addrs[netifaces.AF_INET][0]
            ip_addr = ip_info['addr']

            # Проверяем статус интерфейса
            result = subprocess.run(['ip', 'link', 'show', interface],
                                    capture_output=True, text=True)

            if result.returncode != 0:
                return None

            status = 'up' if 'UP' in result.stdout else 'down'

            # Проверяем это ли USB tethering интерфейс
            is_usb_tethering = (
                interface.startswith('enx') or
                interface.startswith('usb') or
                interface.startswith('rndis') or
                (interface.startswith('enp') and 'u' in interface)
            )

            if not is_usb_tethering:
                return None

            return {
                'interface': interface,
                'ip': ip_addr,
                'netmask': ip_info.get('netmask', ''),
                'status': status,
                'type': 'usb_tethering'
            }

        except Exception as e:
            logger.error(f"Error getting info for interface {interface}: {e}")
            return None

    async def match_android_to_usb_interface(
        self,
        device_id: str,
        device_details: Dict,
        usb_interfaces: List[Dict]
    ) -> Optional[Dict[str, str]]:
        """Сопоставление Android устройства с USB интерфейсом"""
        try:
            # Если есть только один USB интерфейс и одно Android устройство, сопоставляем их
            if len(usb_interfaces) == 1:
                return usb_interfaces[0]

            # Пытаемся определить по MAC адресу или другим характеристикам
            # Пока используем простую логику - берем первый доступный UP интерфейс
            for interface in usb_interfaces:
                if interface['status'] == 'up':
                    return interface

            # Если нет UP интерфейсов, берем первый
            if usb_interfaces:
                return usb_interfaces[0]

        except Exception as e:
            logger.error(f"Error matching Android device {device_id} to USB interface: {e}")

        return None

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

            # Выполняем команды
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

            # Создаем friendly name
            manufacturer = details.get('manufacturer', 'Unknown')
            model = details.get('model', 'Unknown')
            details['friendly_name'] = f"{manufacturer} {model}".strip()

        except Exception as e:
            logger.error(f"Error getting Android device details for {device_id}: {e}")

        return details

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
                            'routing_capable': True,
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
                        'routing_capable': True,
                        'last_seen': datetime.now().isoformat()
                    }
                    logger.info(f"Found Raspberry Pi device on {interface}")

        except Exception as e:
            logger.error("Error discovering Raspberry Pi devices", error=str(e))

        return devices

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

    # Остальные методы остаются без изменений
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
            # Попробуем через USB интерфейс если есть
            usb_interface = device.get('usb_interface')
            if usb_interface:
                try:
                    # Используем curl через интерфейс для получения внешнего IP
                    result = await asyncio.create_subprocess_exec(
                        'curl', '--interface', usb_interface, '-s', '--connect-timeout', '10',
                        'http://httpbin.org/ip',
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, _ = await result.communicate()

                    if result.returncode == 0:
                        import json
                        response = json.loads(stdout.decode())
                        return response.get('origin', '').split(',')[0].strip()
                except Exception as e:
                    logger.warning(f"Failed to get external IP via USB interface: {e}")

            # Fallback: попробуем через ADB
            device_id = device.get('adb_id')
            if device_id:
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
            # Поиск PPP интерфейса
            interfaces = netifaces.interfaces()
            for interface in interfaces:
                if interface.startswith('ppp') or interface.startswith('wwan'):
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        return addrs[netifaces.AF_INET][0]['addr']
        except Exception as e:
            logger.error(f"Error getting USB modem external IP: {e}")

        return None

    async def get_raspberry_external_ip(self, device: dict) -> Optional[str]:
        """Получение внешнего IP Raspberry Pi"""
        try:
            interface = device.get('interface', '')
            if interface and interface in netifaces.interfaces():
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
        routing_capable = len([d for d in self.devices.values() if d.get('routing_capable', False)])

        by_type = {}
        for device in self.devices.values():
            device_type = device.get('type', 'unknown')
            by_type[device_type] = by_type.get(device_type, 0) + 1

        return {
            'total_devices': total,
            'online_devices': online,
            'offline_devices': total - online,
            'routing_capable_devices': routing_capable,
            'devices_by_type': by_type,
            'last_discovery': datetime.now().isoformat()
        }
