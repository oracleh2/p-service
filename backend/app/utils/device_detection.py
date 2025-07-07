# backend/app/utils/device_detection.py
"""
Утилиты для обнаружения и диагностики различных типов устройств
"""

import asyncio
import subprocess
import serial
import netifaces
import json
import aiohttp
from typing import Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger()


class DeviceDetector:
    """Класс для обнаружения различных типов устройств"""

    def __init__(self):
        self.detected_devices = {}

    async def detect_all_devices(self) -> Dict[str, dict]:
        """Обнаружение всех типов устройств"""
        devices = {}

        # Параллельное обнаружение разных типов устройств
        tasks = [
            self.detect_android_devices(),
            self.detect_usb_modems(),
            self.detect_network_modems(),
            self.detect_raspberry_pi_modems()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Объединяем результаты
        for result in results:
            if isinstance(result, dict):
                devices.update(result)
            elif isinstance(result, Exception):
                logger.error(f"Device detection error: {result}")

        self.detected_devices = devices
        return devices

    async def detect_android_devices(self) -> Dict[str, dict]:
        """Обнаружение Android устройств через ADB"""
        devices = {}

        try:
            # Проверяем доступность ADB
            result = await asyncio.create_subprocess_exec(
                'adb', 'version',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            await result.communicate()

            if result.returncode != 0:
                logger.warning("ADB not available")
                return devices

            # Получаем список устройств
            result = await asyncio.create_subprocess_exec(
                'adb', 'devices', '-l',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                logger.error(f"ADB devices command failed: {stderr.decode()}")
                return devices

            # Парсим вывод ADB
            lines = stdout.decode().strip().split('\n')
            if len(lines) < 2:  # Только заголовок
                return devices

            for line in lines[1:]:  # Пропускаем заголовок
                line = line.strip()
                if not line or 'offline' in line:
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    adb_id = parts[0]
                    status = parts[1]

                    if status == 'device':
                        device_info = await self._get_android_device_info(adb_id)

                        # Проверяем USB tethering
                        usb_interface = await self._detect_android_usb_interface(adb_id)

                        device_id = f"android_{adb_id}"
                        devices[device_id] = {
                            'id': device_id,
                            'type': 'android',
                            'adb_id': adb_id,
                            'status': 'online',
                            'interface': usb_interface,
                            'device_info': device_info.get('model', f'Android {adb_id}'),
                            'manufacturer': device_info.get('manufacturer', 'Unknown'),
                            'model': device_info.get('model', 'Unknown'),
                            'android_version': device_info.get('android_version', 'Unknown'),
                            'battery_level': device_info.get('battery_level', 0),
                            'rotation_methods': ['data_toggle', 'airplane_mode', 'usb_reconnect']
                        }

        except Exception as e:
            logger.error(f"Error detecting Android devices: {e}")

        return devices

    async def _get_android_device_info(self, adb_id: str) -> dict:
        """Получение подробной информации об Android устройстве"""
        info = {}

        try:
            # Получаем модель
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'getprop', 'ro.product.model',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                info['model'] = stdout.decode().strip()

            # Получаем производителя
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'getprop', 'ro.product.manufacturer',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                info['manufacturer'] = stdout.decode().strip()

            # Получаем версию Android
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'getprop', 'ro.build.version.release',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                info['android_version'] = stdout.decode().strip()

            # Получаем уровень батареи
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'dumpsys', 'battery',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                battery_output = stdout.decode()
                for line in battery_output.split('\n'):
                    if 'level:' in line:
                        try:
                            level = int(line.split(':')[1].strip())
                            info['battery_level'] = level
                        except:
                            pass

        except Exception as e:
            logger.error(f"Error getting Android device info: {e}")

        return info

    async def _detect_android_usb_interface(self, adb_id: str) -> Optional[str]:
        """Определение USB интерфейса Android устройства"""
        try:
            # Получаем список сетевых интерфейсов
            interfaces = netifaces.interfaces()

            # Ищем интерфейсы, созданные Android устройством
            for interface in interfaces:
                if interface.startswith(('enx', 'usb', 'rndis')):
                    # Проверяем, активен ли интерфейс
                    try:
                        addrs = netifaces.ifaddresses(interface)
                        if netifaces.AF_INET in addrs:
                            # Этот интерфейс может принадлежать нашему устройству
                            return interface
                    except:
                        continue

        except Exception as e:
            logger.error(f"Error detecting Android USB interface: {e}")

        return None

    async def detect_usb_modems(self) -> Dict[str, dict]:
        """Обнаружение USB модемов"""
        devices = {}

        try:
            # Поиск USB устройств через lsusb
            result = await asyncio.create_subprocess_exec(
                'lsusb',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                usb_devices = await self._parse_lsusb_output(stdout.decode())

                # Поиск серийных портов модемов
                serial_ports = await self._find_modem_serial_ports()

                # Объединяем информацию
                for port_info in serial_ports:
                    device_id = f"usb_modem_{port_info['port'].replace('/', '_')}"
                    devices[device_id] = {
                        'id': device_id,
                        'type': 'usb_modem',
                        'status': 'detected',
                        'interface': port_info['port'],
                        'device_info': f"USB Modem on {port_info['port']}",
                        'manufacturer': port_info.get('manufacturer', 'Unknown'),
                        'model': port_info.get('model', 'Unknown'),
                        'rotation_methods': ['at_commands', 'interface_restart', 'usb_reset']
                    }

        except Exception as e:
            logger.error(f"Error detecting USB modems: {e}")

        return devices

    async def _parse_lsusb_output(self, output: str) -> List[dict]:
        """Парсинг вывода lsusb для поиска модемов"""
        modems = []

        # Известные производители модемов
        modem_vendors = [
            'huawei', 'zte', 'sierra', 'qualcomm', 'novatel',
            'option', 'cmotech', 'anydata', 'alcatel'
        ]

        for line in output.split('\n'):
            line = line.lower()
            for vendor in modem_vendors:
                if vendor in line:
                    modems.append({'line': line, 'vendor': vendor})
                    break

        return modems

    async def _find_modem_serial_ports(self) -> List[dict]:
        """Поиск серийных портов модемов"""
        ports = []

        try:
            import glob

            # Поиск типичных портов модемов
            port_patterns = [
                '/dev/ttyUSB*',
                '/dev/ttyACM*',
                '/dev/cdc-wdm*'
            ]

            for pattern in port_patterns:
                found_ports = glob.glob(pattern)
                for port in found_ports:
                    port_info = await self._test_modem_port(port)
                    if port_info:
                        ports.append(port_info)

        except Exception as e:
            logger.error(f"Error finding modem serial ports: {e}")

        return ports

    async def _test_modem_port(self, port: str) -> Optional[dict]:
        """Тестирование серийного порта модема"""
        try:
            # Пытаемся открыть порт и отправить AT команду
            with serial.Serial(port, 115200, timeout=2) as ser:
                ser.write(b'AT\r\n')
                response = ser.read(100)

                if b'OK' in response or b'AT' in response:
                    # Это модем, получаем дополнительную информацию
                    info = {'port': port}

                    # Пытаемся получить модель
                    ser.write(b'AT+CGMI\r\n')
                    manufacturer = ser.read(100)
                    if manufacturer:
                        info['manufacturer'] = manufacturer.decode('utf-8', errors='ignore').strip()

                    ser.write(b'AT+CGMM\r\n')
                    model = ser.read(100)
                    if model:
                        info['model'] = model.decode('utf-8', errors='ignore').strip()

                    return info

        except Exception as e:
            logger.debug(f"Port {port} test failed: {e}")

        return None

    async def detect_network_modems(self) -> Dict[str, dict]:
        """Обнаружение сетевых модемов (PPP, WWAN интерфейсы)"""
        devices = {}

        try:
            interfaces = netifaces.interfaces()

            for interface in interfaces:
                if interface.startswith(('ppp', 'wwan', 'wwp')):
                    device_id = f"network_modem_{interface}"
                    devices[device_id] = {
                        'id': device_id,
                        'type': 'network_device',
                        'status': 'detected',
                        'interface': interface,
                        'device_info': f"Network modem on {interface}",
                        'rotation_methods': ['interface_restart', 'dhcp_renew']
                    }

        except Exception as e:
            logger.error(f"Error detecting network modems: {e}")

        return devices

    async def detect_raspberry_pi_modems(self) -> Dict[str, dict]:
        """Обнаружение модемов на Raspberry Pi"""
        devices = {}

        try:
            # Проверяем, запущены ли мы на Raspberry Pi
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    cpu_info = f.read()
                    if 'BCM' not in cpu_info and 'Raspberry Pi' not in cpu_info:
                        return devices
            except:
                return devices

            # Поиск HAT модемов и USB модемов на RPi
            # Это расширенная логика для Raspberry Pi
            rpi_modems = await self._detect_rpi_hat_modems()
            devices.update(rpi_modems)

        except Exception as e:
            logger.error(f"Error detecting Raspberry Pi modems: {e}")

        return devices

    async def _detect_rpi_hat_modems(self) -> Dict[str, dict]:
        """Обнаружение HAT модемов на Raspberry Pi"""
        devices = {}

        try:
            # Проверяем GPIO и I2C устройства
            # Это упрощенная версия, в реальности нужна более сложная логика

            # Поиск известных HAT модемов
            hat_patterns = [
                '/dev/ttyAMA*',
                '/dev/serial*'
            ]

            import glob
            for pattern in hat_patterns:
                ports = glob.glob(pattern)
                for port in ports:
                    device_id = f"rpi_hat_{port.replace('/', '_')}"
                    devices[device_id] = {
                        'id': device_id,
                        'type': 'raspberry_pi',
                        'status': 'detected',
                        'interface': port,
                        'device_info': f"RPi HAT modem on {port}",
                        'rotation_methods': ['ppp_restart', 'gpio_reset']
                    }

        except Exception as e:
            logger.error(f"Error detecting RPi HAT modems: {e}")

        return devices

    async def test_device_connectivity(self, device_id: str) -> dict:
        """Тестирование подключения устройства"""
        device = self.detected_devices.get(device_id)
        if not device:
            return {"error": "Device not found"}

        device_type = device['type']

        try:
            if device_type == 'android':
                return await self._test_android_connectivity(device)
            elif device_type == 'usb_modem':
                return await self._test_usb_modem_connectivity(device)
            elif device_type in ['network_device', 'raspberry_pi']:
                return await self._test_network_connectivity(device)
            else:
                return {"error": f"Unknown device type: {device_type}"}

        except Exception as e:
            return {"error": str(e)}

    async def _test_android_connectivity(self, device: dict) -> dict:
        """Тестирование подключения Android устройства"""
        adb_id = device['adb_id']

        try:
            # Проверяем ADB соединение
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'echo', 'test',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                return {"success": False, "error": "ADB connection failed"}

            # Проверяем интернет соединение на устройстве
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'ping', '-c', '1', '8.8.8.8',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            await result.communicate()

            internet_available = result.returncode == 0

            # Пытаемся получить внешний IP
            external_ip = await self._get_android_external_ip(adb_id)

            return {
                "success": True,
                "adb_connected": True,
                "internet_available": internet_available,
                "external_ip": external_ip,
                "usb_interface": device.get('interface'),
                "battery_level": device.get('battery_level', 0)
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_android_external_ip(self, adb_id: str) -> Optional[str]:
        """Получение внешнего IP Android устройства"""
        try:
            result = await asyncio.create_subprocess_exec(
                'adb', '-s', adb_id, 'shell', 'curl', '-s', '--max-time', '10', 'https://httpbin.org/ip',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                import json
                data = json.loads(stdout.decode())
                return data.get('origin', '').split(',')[0].strip()

        except Exception as e:
            logger.debug(f"Error getting Android external IP: {e}")

        return None

    async def _test_usb_modem_connectivity(self, device: dict) -> dict:
        """Тестирование подключения USB модема"""
        port = device['interface']

        try:
            with serial.Serial(port, 115200, timeout=5) as ser:
                # Проверяем ответ модема
                ser.write(b'AT\r\n')
                response = ser.read(100)

                if b'OK' not in response:
                    return {"success": False, "error": "Modem not responding"}

                # Проверяем сигнал
                ser.write(b'AT+CSQ\r\n')
                signal_response = ser.read(100)

                # Проверяем статус сети
                ser.write(b'AT+CREG?\r\n')
                network_response = ser.read(100)

                return {
                    "success": True,
                    "modem_responding": True,
                    "signal_info": signal_response.decode('utf-8', errors='ignore').strip(),
                    "network_status": network_response.decode('utf-8', errors='ignore').strip()
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _test_network_connectivity(self, device: dict) -> dict:
        """Тестирование сетевого подключения"""
        interface = device['interface']

        try:
            # Проверяем статус интерфейса
            addrs = netifaces.ifaddresses(interface)

            has_ip = netifaces.AF_INET in addrs
            ip_address = None

            if has_ip:
                ip_address = addrs[netifaces.AF_INET][0]['addr']

            return {
                "success": True,
                "interface_up": has_ip,
                "ip_address": ip_address,
                "interface": interface
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


# Глобальный экземпляр детектора
_device_detector: Optional[DeviceDetector] = None


def get_device_detector() -> DeviceDetector:
    """Получение глобального экземпляра детектора устройств"""
    global _device_detector
    if _device_detector is None:
        _device_detector = DeviceDetector()
    return _device_detector
