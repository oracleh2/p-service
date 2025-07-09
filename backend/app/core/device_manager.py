# backend/app/core/device_manager.py - ОЧИЩЕННАЯ ВЕРСИЯ ДЛЯ ANDROID УСТРОЙСТВ

import asyncio
import subprocess
import time
import re
import json
import netifaces
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
import structlog
import random
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from ..models.database import AsyncSessionLocal
from ..models.base import ProxyDevice

logger = structlog.get_logger()


class DeviceManager:
    """Менеджер Android устройств с поддержкой USB интерфейсов"""

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
        """Обнаружение всех Android устройств с сохранением в БД"""
        try:
            # Очищаем старый список
            self.devices.clear()

            logger.info("Starting Android device discovery...")

            # Обнаружение Android устройств с USB интерфейсами
            android_devices = await self.discover_android_devices_with_interfaces()

            # Объединение всех найденных устройств
            for device_id, device_info in android_devices.items():
                # Сохраняем в память
                self.devices[device_id] = device_info

                logger.info(
                    "Android device discovered",
                    device_id=device_id,
                    type=device_info['type'],
                    interface=device_info.get('usb_interface', device_info.get('interface', 'N/A')),
                    info=device_info.get('device_info', 'Unknown')
                )

                # Сохраняем в базу данных
                await self.save_device_to_db(device_id, device_info)

            logger.info(f"✅ Total Android devices discovered: {len(self.devices)}")
            logger.info(f"✅ Devices saved to database")

        except Exception as e:
            logger.error("Error discovering Android devices", error=str(e))

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

    async def save_device_to_db(self, device_id: str, device_info: dict):
        """Сохранение информации об устройстве в базу данных"""
        try:
            async with AsyncSessionLocal() as db:
                # Проверяем, существует ли устройство в БД
                stmt = select(ProxyDevice).where(ProxyDevice.name == device_id)
                result = await db.execute(stmt)
                existing_device = result.scalar_one_or_none()

                # Определяем тип устройства
                device_type = device_info.get('type', 'android')

                # Получаем IP адрес интерфейса
                ip_address = "0.0.0.0"
                interface = device_info.get('usb_interface') or device_info.get('interface', 'unknown')

                if interface and interface != 'unknown':
                    # Пробуем получить IP интерфейса
                    try:
                        import netifaces
                        if interface in netifaces.interfaces():
                            addrs = netifaces.ifaddresses(interface)
                            if netifaces.AF_INET in addrs:
                                ip_address = addrs[netifaces.AF_INET][0]['addr']
                    except:
                        pass

                # Получаем внешний IP
                external_ip = await self.get_device_external_ip(device_id)

                if existing_device:
                    # Обновляем существующее устройство
                    stmt = update(ProxyDevice).where(
                        ProxyDevice.name == device_id
                    ).values(
                        device_type=device_type,
                        ip_address=ip_address,
                        status=device_info.get('status', 'offline'),
                        current_external_ip=external_ip,
                        operator=device_info.get('operator', 'Unknown'),
                        last_heartbeat=datetime.now()
                    )
                    await db.execute(stmt)
                    logger.info(f"Updated Android device {device_id} in database")
                else:
                    # Создаем новое устройство с уникальным портом
                    unique_port = await self.get_next_available_port(db)

                    new_device = ProxyDevice(
                        name=device_id,
                        device_type=device_type,
                        ip_address=ip_address,
                        port=unique_port,
                        status=device_info.get('status', 'offline'),
                        current_external_ip=external_ip,
                        operator=device_info.get('operator', 'Unknown'),
                        region=device_info.get('region', 'Unknown'),
                        rotation_interval=600
                    )
                    db.add(new_device)
                    logger.info(f"Created new Android device {device_id} in database with port {unique_port}")

                await db.commit()

        except Exception as e:
            logger.error(
                "Error saving Android device to database",
                device_id=device_id,
                error=str(e)
            )

    async def get_next_available_port(self, db: AsyncSession, start_port: int = 9000, max_port: int = 65535) -> int:
        """Получение следующего доступного порта с проверкой доступности"""
        try:
            # Получаем максимальный используемый порт
            stmt = select(func.max(ProxyDevice.port)).where(
                ProxyDevice.port.between(start_port, max_port)
            )
            result = await db.execute(stmt)
            max_used_port = result.scalar()

            if max_used_port is None:
                return start_port

            # Начинаем поиск с max_used_port + 1
            candidate_port = max(max_used_port + 1, start_port)

            # Проверяем доступность портов
            for port in range(candidate_port, max_port + 1):
                if not await self.is_port_used(db, port):
                    logger.info(f"Selected next available port: {port}")
                    return port

            # Если не нашли свободный порт, ищем пропуски
            for port in range(start_port, max_used_port):
                if not await self.is_port_used(db, port):
                    logger.info(f"Found gap in port range, using: {port}")
                    return port

            raise RuntimeError(f"No available ports in range {start_port}-{max_port}")

        except Exception as e:
            logger.error(f"Error finding available port: {e}")
            import random
            fallback_port = random.randint(start_port, max_port)
            logger.warning(f"Using fallback random port: {fallback_port}")
            return fallback_port

    async def is_port_used(self, db: AsyncSession, port: int) -> bool:
        """Проверка, используется ли порт другим устройством"""
        try:
            stmt = select(ProxyDevice.id).where(ProxyDevice.port == port)
            result = await db.execute(stmt)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Error checking port usage: {e}")
            return True

    # Методы для получения информации об устройствах
    async def get_all_devices(self) -> Dict[str, Dict[str, Any]]:
        """Получение всех Android устройств"""
        return self.devices.copy()

    async def get_device_by_id(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Получение Android устройства по ID"""
        return self.devices.get(device_id)

    async def get_available_devices(self) -> List[dict]:
        """Получение доступных (онлайн) Android устройств"""
        return [device for device in self.devices.values() if device.get('status') == 'online']

    async def get_random_device(self) -> Optional[Dict[str, Any]]:
        """Получение случайного онлайн Android устройства"""
        online_devices = [
            device for device in self.devices.values()
            if device.get('status') == 'online'
        ]

        if not online_devices:
            return None

        return random.choice(online_devices)

    async def is_device_online(self, device_id: str) -> bool:
        """Проверка онлайн статуса Android устройства"""
        device = self.devices.get(device_id)
        return device is not None and device.get('status') == 'online'

    async def get_device_external_ip(self, device_id: str) -> Optional[str]:
        """Получение внешнего IP Android устройства"""
        device = self.devices.get(device_id)
        if not device:
            return None

        try:
            return await self.get_android_external_ip(device)
        except Exception as e:
            logger.error(f"Error getting external IP for {device_id}: {e}")
            return None

    async def get_android_external_ip(self, device: Dict[str, Any]) -> Optional[str]:
        """Получение внешнего IP Android устройства через USB интерфейс"""
        try:
            interface = device.get('interface') or device.get('usb_interface')
            adb_id = device.get('adb_id')

            if not interface or interface == "unknown":
                logger.warning(f"No USB interface for Android device {adb_id}")
                # Пытаемся найти интерфейс заново
                interface = await self.find_android_usb_interface(adb_id)
                if interface:
                    device['interface'] = interface
                    device['status'] = 'online'
                    device['usb_tethering'] = True
                    logger.info(f"Found and updated interface for {adb_id}: {interface}")
                else:
                    return None

            # Метод 1: Через curl с привязкой к интерфейсу
            try:
                result = await asyncio.create_subprocess_exec(
                    'curl', '--interface', interface, '-s', '--connect-timeout', '10',
                    'httpbin.org/ip',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()

                if result.returncode == 0:
                    try:
                        import json
                        response = json.loads(stdout.decode())
                        external_ip = response.get('origin')
                        if external_ip:
                            logger.debug(f"Got external IP for {adb_id} via interface {interface}: {external_ip}")
                            return external_ip
                    except json.JSONDecodeError:
                        # Пробуем найти IP в тексте
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', stdout.decode())
                        if ip_match:
                            return ip_match.group(1)
            except Exception as e:
                logger.debug(f"Method 1 failed for {adb_id}: {e}")

            # Метод 2: Через ADB (резервный)
            try:
                result = await asyncio.create_subprocess_exec(
                    'adb', '-s', adb_id, 'shell', 'curl', '-s', '--connect-timeout', '5', 'httpbin.org/ip',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()

                if result.returncode == 0:
                    try:
                        import json
                        response = json.loads(stdout.decode())
                        external_ip = response.get('origin')
                        if external_ip:
                            logger.debug(f"Got external IP for {adb_id} via ADB: {external_ip}")
                            return external_ip
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                logger.debug(f"Method 2 failed for {adb_id}: {e}")

            logger.warning(f"All methods failed to get external IP for Android device {adb_id}")
            return None

        except Exception as e:
            logger.error(f"Error getting Android external IP: {e}")
            return None

    async def find_android_usb_interface(self, device_id: str) -> Optional[str]:
        """Автоматическое определение USB интерфейса для Android устройства"""
        logger.info(f"Searching USB interface for Android device {device_id}")

        try:
            # Получаем список всех сетевых интерфейсов
            all_interfaces = netifaces.interfaces()
            logger.debug(f"All network interfaces: {all_interfaces}")

            # Возможные шаблоны имен USB интерфейсов для Android
            android_patterns = [
                r'^usb\d+$',
                r'^rndis\d+$',
                r'^enx[0-9a-f]{12}$',
                r'^enp\d+s\d+u\d+$',
            ]

            # Находим кандидатов среди интерфейсов
            candidate_interfaces = []

            for interface in all_interfaces:
                for pattern in android_patterns:
                    if re.match(pattern, interface):
                        # Проверяем, что интерфейс активен и имеет IP
                        if self._interface_has_ip(interface):
                            candidate_interfaces.append(interface)
                            logger.debug(f"Found candidate interface: {interface}")

            if not candidate_interfaces:
                logger.warning(f"No active USB interfaces found for device {device_id}")
                return None

            # Если есть несколько кандидатов, выбираем лучший
            if len(candidate_interfaces) == 1:
                interface = candidate_interfaces[0]
                logger.info(f"Found USB interface for {device_id}: {interface}")
                return interface

            # Если несколько интерфейсов, проверяем какой подключен к нашему устройству
            for interface in candidate_interfaces:
                if await self._verify_interface_belongs_to_device(interface, device_id):
                    logger.info(f"Verified USB interface for {device_id}: {interface}")
                    return interface

            # Если не удалось определить однозначно, берем первый
            interface = candidate_interfaces[0]
            logger.warning(f"Using first candidate interface for {device_id}: {interface}")
            return interface

        except Exception as e:
            logger.error(f"Error finding USB interface for {device_id}: {e}")
            return None

    def _interface_has_ip(self, interface: str) -> bool:
        """Проверка наличия IP адреса на интерфейсе"""
        try:
            addresses = netifaces.ifaddresses(interface)
            return netifaces.AF_INET in addresses and len(addresses[netifaces.AF_INET]) > 0
        except Exception:
            return False

    async def _verify_interface_belongs_to_device(self, interface: str, device_id: str) -> bool:
        """Проверка принадлежности интерфейса к конкретному Android устройству"""
        try:
            # Получаем внешний IP через ADB
            adb_result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'curl', '-s', '--connect-timeout', '5', 'httpbin.org/ip',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            adb_stdout, _ = await adb_result.communicate()

            if adb_result.returncode != 0:
                return False

            # Получаем внешний IP через интерфейс
            interface_result = await asyncio.create_subprocess_exec(
                'curl', '--interface', interface, '-s', '--connect-timeout', '5', 'httpbin.org/ip',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            interface_stdout, _ = await interface_result.communicate()

            if interface_result.returncode != 0:
                return False

            # Сравниваем IP адреса
            try:
                import json
                adb_data = json.loads(adb_stdout.decode())
                interface_data = json.loads(interface_stdout.decode())

                adb_ip = adb_data.get('origin', '')
                interface_ip = interface_data.get('origin', '')

                return adb_ip == interface_ip and adb_ip != ''
            except (json.JSONDecodeError, KeyError):
                return False

        except Exception as e:
            logger.debug(f"Error verifying interface {interface} for device {device_id}: {e}")
            return False

    async def update_device_status(self, device_id: str, status: str):
        """Обновление статуса устройства в памяти и БД"""
        try:
            # Обновляем в памяти
            if device_id in self.devices:
                self.devices[device_id]['status'] = status
                self.devices[device_id]['last_seen'] = datetime.now(timezone.utc).isoformat()

            # Обновляем в БД
            async with AsyncSessionLocal() as db:
                stmt = update(ProxyDevice).where(
                    ProxyDevice.name == device_id
                ).values(
                    status=status,
                    last_heartbeat=datetime.now()
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error(f"Error updating device status: {e}")

    async def get_devices_from_db(self) -> List[dict]:
        """Получение списка Android устройств из базы данных"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice).where(ProxyDevice.device_type == 'android')
                result = await db.execute(stmt)
                devices = result.scalars().all()

                devices_list = []
                for device in devices:
                    device_data = {
                        "id": str(device.id),
                        "name": device.name,
                        "device_type": device.device_type,
                        "ip_address": device.ip_address,
                        "port": device.port,
                        "status": device.status,
                        "current_external_ip": device.current_external_ip,
                        "operator": device.operator,
                        "region": device.region,
                        "last_heartbeat": device.last_heartbeat,
                        "rotation_interval": device.rotation_interval,
                        "proxy_enabled": device.proxy_enabled or False,
                        "dedicated_port": device.dedicated_port,
                        "proxy_username": device.proxy_username,
                        "proxy_password": device.proxy_password
                    }
                    devices_list.append(device_data)

                return devices_list

        except Exception as e:
            logger.error(f"Error getting Android devices from database: {e}")
            return []

    async def sync_devices_with_db(self):
        """Синхронизация обнаруженных устройств с базой данных"""
        try:
            logger.info("Syncing discovered Android devices with database...")

            for device_id, device_info in self.devices.items():
                await self.save_device_to_db(device_id, device_info)

            logger.info("✅ Android device synchronization completed")

        except Exception as e:
            logger.error(f"Error syncing Android devices with database: {e}")

    async def force_sync_to_db(self):
        """Принудительная синхронизация всех Android устройств с БД"""
        logger.info("🔄 Starting forced Android device synchronization to database...")
        await self.sync_devices_with_db()
        return len(self.devices)

    async def get_summary(self) -> Dict[str, any]:
        """Получение сводной информации об Android устройствах"""
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

    async def get_device_proxy_route(self, device_id: str) -> Optional[dict]:
        """Получение маршрута для проксирования через Android устройство"""
        all_devices = await self.get_all_devices()
        device = all_devices.get(device_id)

        if not device:
            return None

        interface = device.get('interface') or device.get('usb_interface')
        if interface:
            return {
                'type': 'android_usb',
                'interface': interface,
                'method': 'interface_binding',
                'device_id': device.get('adb_id')
            }

        return None
