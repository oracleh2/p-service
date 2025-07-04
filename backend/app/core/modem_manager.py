import asyncio
import serial
import subprocess
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import structlog
import re
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
                    interface=modem_info['interface']
                )

        except Exception as e:
            logger.error("Error discovering modems", error=str(e))

    async def discover_usb_modems(self) -> Dict[str, dict]:
        """Обнаружение USB 4G модемов"""
        modems = {}

        try:
            # Поиск USB модемов через lsusb
            result = await asyncio.create_subprocess_exec(
                'lsusb', stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()

            usb_devices = stdout.decode().split('\n')

            # Известные производители модемов
            modem_vendors = [
                'Huawei', 'ZTE', 'Quectel', 'Sierra Wireless',
                'Novatel', 'Option', 'Telit', 'u-blox'
            ]

            for line in usb_devices:
                for vendor in modem_vendors:
                    if vendor.lower() in line.lower():
                        # Попытка найти последовательный порт
                        serial_port = await self.find_modem_serial_port(line)
                        if serial_port:
                            modem_id = f"usb_{len(modems)}"
                            modems[modem_id] = {
                                'id': modem_id,
                                'type': 'usb_modem',
                                'vendor': vendor,
                                'interface': serial_port,
                                'device_info': line.strip(),
                                'status': 'detected'
                            }
                            break

        except Exception as e:
            logger.error("Error discovering USB modems", error=str(e))

        return modems

    async def discover_android_devices(self) -> Dict[str, dict]:
        """Обнаружение Android устройств через ADB"""
        modems = {}

        try:
            # Проверка доступности ADB
            result = await asyncio.create_subprocess_exec(
                'adb', 'devices', stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()

            if result.returncode == 0:
                devices = stdout.decode().split('\n')[1:]  # Пропускаем заголовок

                for line in devices:
                    if line.strip() and '\tdevice' in line:
                        device_id = line.split('\t')[0]
                        modem_id = f"android_{device_id}"

                        # Проверка поддержки USB tethering
                        if await self.check_android_tethering(device_id):
                            modems[modem_id] = {
                                'id': modem_id,
                                'type': 'android',
                                'interface': device_id,
                                'device_info': f"Android device {device_id}",
                                'status': 'detected',
                                'adb_id': device_id
                            }

        except Exception as e:
            logger.error("Error discovering Android devices", error=str(e))

        return modems

    async def discover_network_modems(self) -> Dict[str, dict]:
        """Обнаружение сетевых модемов (Raspberry Pi и др.)"""
        modems = {}

        try:
            # Поиск устройств в локальной сети с открытым портом модема
            # (это упрощенная версия, в реальности нужно более сложное сканирование)

            # Получение локальных сетевых интерфейсов
            interfaces = netifaces.interfaces()

            for interface in interfaces:
                if interface.startswith('ppp') or interface.startswith('wwan'):
                    # Это может быть PPP соединение от модема
                    modem_id = f"network_{interface}"
                    modems[modem_id] = {
                        'id': modem_id,
                        'type': 'network_modem',
                        'interface': interface,
                        'device_info': f"Network interface {interface}",
                        'status': 'detected'
                    }

        except Exception as e:
            logger.error("Error discovering network modems", error=str(e))

        return modems

    async def find_modem_serial_port(self, usb_line: str) -> Optional[str]:
        """Поиск последовательного порта для USB модема"""
        try:
            # Поиск устройств в /dev/ttyUSB* или /dev/ttyACM*
            import glob

            usb_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')

            for port in usb_ports:
                try:
                    # Попытка подключения и отправки AT команды
                    ser = serial.Serial(port, 115200, timeout=1)
                    ser.write(b'AT\r\n')
                    response = ser.read(100)
                    ser.close()

                    if b'OK' in response:
                        return port
                except:
                    continue

        except Exception as e:
            logger.error("Error finding serial port", error=str(e))

        return None

    async def check_android_tethering(self, device_id: str) -> bool:
        """Проверка поддержки USB tethering на Android"""
        try:
            # Проверка наличия настроек tethering
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell',
                'settings', 'get', 'global', 'tether_supported',
                stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()

            return stdout.decode().strip() == '1'

        except Exception:
            return False

    async def rotate_modem_ip(self, modem_id: str) -> bool:
        """Ротация IP модема"""
        if modem_id not in self.modems:
            logger.error("Modem not found", modem_id=modem_id)
            return False

        modem = self.modems[modem_id]

        try:
            if modem['type'] == 'usb_modem':
                return await self.rotate_usb_modem(modem)
            elif modem['type'] == 'android':
                return await self.rotate_android_modem(modem)
            elif modem['type'] == 'network_modem':
                return await self.rotate_network_modem(modem)
            else:
                logger.error("Unknown modem type", modem_id=modem_id, type=modem['type'])
                return False

        except Exception as e:
            logger.error("Error rotating modem IP", modem_id=modem_id, error=str(e))
            return False

    async def rotate_usb_modem(self, modem: dict) -> bool:
        """Ротация IP для USB модема через AT команды"""
        try:
            serial_port = modem['interface']

            # Подключение к модему
            ser = serial.Serial(serial_port, 115200, timeout=10)

            logger.info("Starting USB modem rotation", modem_id=modem['id'])

            # Отключение от сети
            ser.write(b'AT+CFUN=0\r\n')
            response = ser.read(100)

            if b'OK' not in response:
                logger.error("Failed to disable modem radio", modem_id=modem['id'])
                ser.close()
                return False

            # Ожидание
            await asyncio.sleep(5)

            # Включение радио
            ser.write(b'AT+CFUN=1\r\n')
            response = ser.read(100)

            if b'OK' not in response:
                logger.error("Failed to enable modem radio", modem_id=modem['id'])
                ser.close()
                return False

            ser.close()

            # Ожидание подключения к сети
            await asyncio.sleep(15)

            logger.info("USB modem rotation completed", modem_id=modem['id'])
            return True

        except Exception as e:
            logger.error("Error in USB modem rotation", modem_id=modem['id'], error=str(e))
            return False

    async def rotate_android_modem(self, modem: dict) -> bool:
        """Ротация IP для Android устройства через ADB"""
        try:
            device_id = modem['adb_id']

            logger.info("Starting Android modem rotation", modem_id=modem['id'])

            # Отключение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'svc', 'data', 'disable'
            )
            await result.wait()

            # Ожидание
            await asyncio.sleep(3)

            # Включение мобильных данных
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'svc', 'data', 'enable'
            )
            await result.wait()

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
        """Получение IP Android устройства"""
        try:
            device_id = modem['adb_id']

            # Получение IP через ADB
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', device_id, 'shell', 'ip', 'route', 'get', '8.8.8.8',
                stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()

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

    async def get_modem_status(self, modem_id: str) -> dict:
        """Получение статуса модема"""
        if modem_id not in self.modems:
            return {"error": "Modem not found"}

        modem = self.modems[modem_id]

        try:
            # Получение базовой информации
            status = {
                "modem_id": modem_id,
                "type": modem['type'],
                "interface": modem['interface'],
                "device_info": modem['device_info'],
                "status": modem['status']
            }

            # Получение IP адреса
            external_ip = await self.get_modem_external_ip(modem_id)
            status["external_ip"] = external_ip

            # Дополнительная информация в зависимости от типа
            if modem['type'] == 'usb_modem':
                status.update(await self.get_usb_modem_details(modem))
            elif modem['type'] == 'android':
                status.update(await self.get_android_modem_details(modem))

            return status

        except Exception as e:
            logger.error("Error getting modem status", modem_id=modem_id, error=str(e))
            return {"error": str(e)}

    async def get_usb_modem_details(self, modem: dict) -> dict:
        """Получение детальной информации о USB модеме"""
        try:
            serial_port = modem['interface']
            ser = serial.Serial(serial_port, 115200, timeout=5)

            details = {}

            # Получение информации о модеме
            commands = {
                'manufacturer': 'AT+CGMI',
                'model': 'AT+CGMM',
                'imei': 'AT+CGSN',
                'signal_strength': 'AT+CSQ',
                'network_registration': 'AT+CREG?'
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