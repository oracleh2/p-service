# backend/app/core/modem_manager.py - МЕНЕДЖЕР ДЛЯ HUAWEI E3372h МОДЕМОВ

import asyncio
import subprocess
import time
import re
import json
import netifaces
import aiohttp
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


class ModemManager:
    """Менеджер для работы с USB модемами Huawei E3372h"""

    def __init__(self):
        self.modems: Dict[str, dict] = {}
        self.running = False
        self.huawei_oui = "0c:5b:8f"  # Официальный OUI Huawei Technologies Co.,Ltd.

    async def start(self):
        """Запуск менеджера модемов"""
        self.running = True
        await self.discover_all_devices()
        logger.info("Modem manager started")

    async def stop(self):
        """Остановка менеджера модемов"""
        self.running = False
        logger.info("Modem manager stopped")

    async def discover_all_devices(self):
        """Обнаружение всех Huawei E3372h модемов с сохранением в БД"""
        try:
            # Очищаем старый список
            self.modems.clear()

            logger.info("Starting Huawei E3372h modem discovery...")

            # Обнаружение USB модемов Huawei
            huawei_modems = await self.discover_huawei_modems()

            # Объединение всех найденных модемов
            for modem_id, modem_info in huawei_modems.items():
                # Сохраняем в память
                self.modems[modem_id] = modem_info

                logger.info(
                    "Huawei modem discovered",
                    modem_id=modem_id,
                    type=modem_info['type'],
                    interface=modem_info.get('interface', 'N/A'),
                    web_interface=modem_info.get('web_interface', 'N/A'),
                    info=modem_info.get('device_info', 'Unknown')
                )

                # Сохраняем в базу данных
                await self.save_device_to_db(modem_id, modem_info)

            logger.info(f"✅ Total Huawei modems discovered: {len(self.modems)}")
            logger.info(f"✅ Modems saved to database")

        except Exception as e:
            logger.error("Error discovering Huawei modems", error=str(e))

    async def discover_huawei_modems(self) -> Dict[str, dict]:
        """Обнаружение Huawei E3372h модемов по MAC-адресу"""
        modems = {}

        try:
            logger.info("Scanning for Huawei E3372h modems by MAC address...")

            # Получаем все сетевые интерфейсы
            all_interfaces = netifaces.interfaces()

            for interface in all_interfaces:
                try:
                    # Получаем MAC-адрес интерфейса
                    mac_addr = await self.get_interface_mac(interface)
                    if not mac_addr:
                        continue

                    # Проверяем, является ли это Huawei устройством
                    if not mac_addr.lower().startswith(self.huawei_oui.lower()):
                        continue

                    logger.info(f"Found Huawei interface: {interface} with MAC: {mac_addr}")

                    # Получаем IP-адрес интерфейса
                    interface_ip = await self.get_interface_ip(interface)
                    if not interface_ip:
                        logger.warning(f"No IP address for Huawei interface {interface}")
                        continue

                    # Извлекаем номер подсети из IP (например, 192.168.108.100 -> 108)
                    subnet_number = await self.extract_subnet_number(interface_ip)
                    if subnet_number is None:
                        logger.warning(f"Cannot extract subnet number from IP {interface_ip}")
                        continue

                    # Формируем адрес веб-интерфейса
                    web_interface = f"192.168.{subnet_number}.1"

                    # Проверяем доступность веб-интерфейса
                    web_accessible = await self.check_web_interface_accessibility(web_interface)

                    # Получаем детальную информацию о модеме
                    modem_details = await self.get_modem_details(web_interface, interface_ip)

                    modem_id = f"huawei_{interface}"
                    modem_info = {
                        'id': modem_id,
                        'type': 'usb_modem',
                        'model': 'E3372h',
                        'manufacturer': 'Huawei',
                        'interface': interface,
                        'mac_address': mac_addr,
                        'interface_ip': interface_ip,
                        'web_interface': web_interface,
                        'subnet_number': subnet_number,
                        'device_info': f"Huawei E3372h on {interface} (subnet {subnet_number})",
                        'status': 'online' if web_accessible else 'offline',
                        'web_accessible': web_accessible,
                        'routing_capable': True,
                        'last_seen': datetime.now().isoformat()
                    }

                    # Добавляем детальную информацию если получена
                    if modem_details:
                        modem_info.update(modem_details)

                    modems[modem_id] = modem_info

                    logger.info(
                        f"✅ Huawei E3372h discovered: {interface} -> {web_interface} "
                        f"(subnet {subnet_number}, web {'accessible' if web_accessible else 'not accessible'})"
                    )

                except Exception as e:
                    logger.warning(f"Error processing interface {interface}: {e}")
                    continue

        except Exception as e:
            logger.error("Error discovering Huawei modems", error=str(e))

        return modems

    async def get_interface_mac(self, interface: str) -> Optional[str]:
        """Получение MAC-адреса интерфейса"""
        try:
            # Метод 1: через netifaces
            try:
                interface_info = netifaces.ifaddresses(interface)
                if netifaces.AF_LINK in interface_info:
                    link_info = interface_info[netifaces.AF_LINK][0]
                    mac_addr = link_info.get('addr')
                    if mac_addr and mac_addr != '00:00:00:00:00:00':
                        return mac_addr
            except Exception:
                pass

            # Метод 2: через ip command
            try:
                result = await asyncio.create_subprocess_exec(
                    'ip', 'link', 'show', interface,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await result.communicate()

                if result.returncode == 0:
                    output = stdout.decode()
                    mac_match = re.search(r'link/ether ([0-9a-f:]{17})', output)
                    if mac_match:
                        return mac_match.group(1)
            except Exception:
                pass

            # Метод 3: через /sys/class/net
            try:
                with open(f'/sys/class/net/{interface}/address', 'r') as f:
                    mac_addr = f.read().strip()
                    if mac_addr and mac_addr != '00:00:00:00:00:00':
                        return mac_addr
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Error getting MAC for interface {interface}: {e}")

        return None

    async def get_interface_ip(self, interface: str) -> Optional[str]:
        """Получение IP-адреса интерфейса"""
        try:
            if interface not in netifaces.interfaces():
                return None

            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET not in addrs:
                return None

            ip_info = addrs[netifaces.AF_INET][0]
            return ip_info['addr']

        except Exception as e:
            logger.debug(f"Error getting IP for interface {interface}: {e}")
            return None

    async def extract_subnet_number(self, ip_address: str) -> Optional[int]:
        """Извлечение номера подсети из IP-адреса (например, 192.168.108.100 -> 108)"""
        try:
            # Ожидаем формат 192.168.XXX.100
            parts = ip_address.split('.')
            if len(parts) == 4 and parts[0] == '192' and parts[1] == '168':
                return int(parts[2])
        except Exception as e:
            logger.debug(f"Error extracting subnet number from {ip_address}: {e}")

        return None

    async def check_web_interface_accessibility(self, web_interface: str) -> bool:
        """Проверка доступности веб-интерфейса модема"""
        try:
            url = f"http://{web_interface}"
            timeout = aiohttp.ClientTimeout(total=5)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    return response.status == 200
        except Exception as e:
            logger.debug(f"Web interface {web_interface} not accessible: {e}")
            return False

    async def get_modem_details(self, web_interface: str, interface_ip: str) -> Optional[Dict[str, Any]]:
        """Получение детальной информации о модеме через веб-интерфейс"""
        details = {}

        try:
            # Получаем внешний IP через интерфейс
            external_ip = await self.get_external_ip_via_interface(interface_ip)
            if external_ip:
                details['external_ip'] = external_ip

            # Пытаемся получить дополнительную информацию через веб-интерфейс
            # Это может потребовать авторизации, поэтому пока оставляем базовую информацию
            details.update({
                'signal_strength': 'N/A',
                'operator': 'Unknown',
                'technology': '4G LTE',
                'connection_status': 'Connected' if external_ip else 'Disconnected'
            })

        except Exception as e:
            logger.debug(f"Error getting modem details for {web_interface}: {e}")

        return details if details else None

    async def get_external_ip_via_interface(self, interface_ip: str) -> Optional[str]:
        """Получение внешнего IP через интерфейс модема"""
        try:
            # Найдем интерфейс по IP
            interface_name = None
            for interface in netifaces.interfaces():
                ip = await self.get_interface_ip(interface)
                if ip == interface_ip:
                    interface_name = interface
                    break

            if not interface_name:
                return None

            # Получаем внешний IP через curl с привязкой к интерфейсу
            result = await asyncio.create_subprocess_exec(
                'curl', '--interface', interface_name, '-s', '--connect-timeout', '10',
                'https://httpbin.org/ip',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                try:
                    import json
                    response = json.loads(stdout.decode())
                    return response.get('origin', '').split(',')[0].strip()
                except json.JSONDecodeError:
                    # Пробуем найти IP в тексте
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', stdout.decode())
                    if ip_match:
                        return ip_match.group(1)

        except Exception as e:
            logger.debug(f"Error getting external IP via interface {interface_ip}: {e}")

        return None

    async def save_device_to_db(self, modem_id: str, modem_info: dict):
        """Сохранение информации о модеме в базу данных"""
        try:
            async with AsyncSessionLocal() as db:
                # Проверяем, существует ли модем в БД
                stmt = select(ProxyDevice).where(ProxyDevice.name == modem_id)
                result = await db.execute(stmt)
                existing_device = result.scalar_one_or_none()

                # Определяем тип устройства
                device_type = modem_info.get('type', 'usb_modem')

                # IP адрес интерфейса
                ip_address = modem_info.get('interface_ip', '0.0.0.0')

                # Получаем внешний IP
                external_ip = modem_info.get('external_ip')

                if existing_device:
                    # Обновляем существующий модем
                    stmt = update(ProxyDevice).where(
                        ProxyDevice.name == modem_id
                    ).values(
                        device_type=device_type,
                        ip_address=ip_address,
                        status=modem_info.get('status', 'offline'),
                        current_external_ip=external_ip,
                        operator=modem_info.get('operator', 'Unknown'),
                        last_heartbeat=datetime.now()  # Убираем timezone.utc
                    )
                    await db.execute(stmt)
                    logger.info(f"Updated Huawei modem {modem_id} in database")
                else:
                    # Создаем новый модем с уникальным портом
                    unique_port = await self.get_next_available_port(db)

                    new_device = ProxyDevice(
                        name=modem_id,
                        device_type=device_type,
                        ip_address=ip_address,
                        port=unique_port,
                        status=modem_info.get('status', 'offline'),
                        current_external_ip=external_ip,
                        operator=modem_info.get('operator', 'Unknown'),
                        region=modem_info.get('region', 'Unknown'),
                        rotation_interval=600
                    )
                    db.add(new_device)
                    logger.info(f"Created new Huawei modem {modem_id} in database with port {unique_port}")

                await db.commit()

        except Exception as e:
            logger.error(
                "Error saving Huawei modem to database",
                modem_id=modem_id,
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

    # Методы для получения информации о модемах (аналогично DeviceManager)
    async def get_all_devices(self) -> Dict[str, Dict[str, Any]]:
        """Получение всех модемов"""
        return self.modems.copy()

    async def get_device_by_id(self, modem_id: str) -> Optional[Dict[str, Any]]:
        """Получение модема по ID"""
        return self.modems.get(modem_id)

    async def get_available_devices(self) -> List[dict]:
        """Получение доступных (онлайн) модемов"""
        return [modem for modem in self.modems.values() if modem.get('status') == 'online']

    async def get_random_device(self) -> Optional[Dict[str, Any]]:
        """Получение случайного онлайн модема"""
        online_modems = [
            modem for modem in self.modems.values()
            if modem.get('status') == 'online'
        ]

        if not online_modems:
            return None

        return random.choice(online_modems)

    async def is_device_online(self, modem_id: str) -> bool:
        """Проверка онлайн статуса модема"""
        modem = self.modems.get(modem_id)
        return modem is not None and modem.get('status') == 'online'

    async def get_device_external_ip(self, modem_id: str) -> Optional[str]:
        """Получение внешнего IP модема"""
        modem = self.modems.get(modem_id)
        if not modem:
            return None

        try:
            # Если IP уже есть в кэше, возвращаем его
            if modem.get('external_ip'):
                return modem['external_ip']

            # Получаем внешний IP через интерфейс
            interface_ip = modem.get('interface_ip')
            if interface_ip:
                external_ip = await self.get_external_ip_via_interface(interface_ip)
                if external_ip:
                    # Обновляем кэш
                    modem['external_ip'] = external_ip
                    return external_ip

        except Exception as e:
            logger.error(f"Error getting external IP for modem {modem_id}: {e}")

        return None

    async def update_device_status(self, modem_id: str, status: str):
        """Обновление статуса модема в памяти и БД"""
        try:
            # Обновляем в памяти
            if modem_id in self.modems:
                self.modems[modem_id]['status'] = status
                self.modems[modem_id]['last_seen'] = datetime.now().isoformat()  # Убираем timezone.utc

            # Обновляем в БД
            async with AsyncSessionLocal() as db:
                stmt = update(ProxyDevice).where(
                    ProxyDevice.name == modem_id
                ).values(
                    status=status,
                    last_heartbeat=datetime.now()  # Убираем timezone.utc
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error(f"Error updating modem status: {e}")

    async def get_devices_from_db(self) -> List[dict]:
        """Получение списка модемов из базы данных"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice).where(ProxyDevice.device_type == 'usb_modem')
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
            logger.error(f"Error getting modems from database: {e}")
            return []

    async def sync_devices_with_db(self):
        """Синхронизация обнаруженных модемов с базой данных"""
        try:
            logger.info("Syncing discovered modems with database...")

            for modem_id, modem_info in self.modems.items():
                await self.save_device_to_db(modem_id, modem_info)

            logger.info("✅ Modem synchronization completed")

        except Exception as e:
            logger.error(f"Error syncing modems with database: {e}")

    async def force_sync_to_db(self):
        """Принудительная синхронизация всех модемов с БД"""
        logger.info("🔄 Starting forced modem synchronization to database...")
        await self.sync_devices_with_db()
        return len(self.modems)

    async def get_summary(self) -> Dict[str, any]:
        """Получение сводной информации о модемах"""
        total = len(self.modems)
        online = len([d for d in self.modems.values() if d.get('status') == 'online'])
        routing_capable = len([d for d in self.modems.values() if d.get('routing_capable', False)])

        by_type = {}
        for modem in self.modems.values():
            device_type = modem.get('type', 'unknown')
            by_type[device_type] = by_type.get(device_type, 0) + 1

        return {
            'total_devices': total,
            'online_devices': online,
            'offline_devices': total - online,
            'routing_capable_devices': routing_capable,
            'devices_by_type': by_type,
            'last_discovery': datetime.now().isoformat()
        }

    async def get_device_proxy_route(self, modem_id: str) -> Optional[dict]:
        """Получение маршрута для проксирования через модем"""
        all_modems = await self.get_all_devices()
        modem = all_modems.get(modem_id)

        if not modem:
            return None

        interface = modem.get('interface')
        if interface:
            return {
                'type': 'usb_modem',
                'interface': interface,
                'method': 'interface_binding',
                'web_interface': modem.get('web_interface')
            }

        return None

    async def get_device_by_operator(self, operator: str) -> Optional[dict]:
        """Получение модема по оператору"""
        for modem in self.modems.values():
            if modem.get('operator', '').lower() == operator.lower() and modem.get('status') == 'online':
                return modem
        return None

    async def get_device_by_region(self, region: str) -> Optional[dict]:
        """Получение модема по региону"""
        for modem in self.modems.values():
            if modem.get('region', '').lower() == region.lower() and modem.get('status') == 'online':
                return modem
        return None

    async def test_modem_connectivity(self, modem_id: str) -> Dict[str, Any]:
        """Тестирование подключения модема"""
        modem = self.modems.get(modem_id)
        if not modem:
            return {"error": "Modem not found"}

        try:
            test_results = {
                "modem_id": modem_id,
                "timestamp": datetime.now().isoformat(),
                "tests": {}
            }

            # Тест 1: Проверка веб-интерфейса
            web_interface = modem.get('web_interface')
            if web_interface:
                web_test = await self.check_web_interface_accessibility(web_interface)
                test_results["tests"]["web_interface"] = {
                    "url": f"http://{web_interface}",
                    "accessible": web_test
                }

            # Тест 2: Проверка внешнего IP
            external_ip = await self.get_device_external_ip(modem_id)
            test_results["tests"]["external_ip"] = {
                "ip": external_ip,
                "available": external_ip is not None
            }

            # Тест 3: Ping test через интерфейс
            interface = modem.get('interface')
            if interface:
                ping_test = await self.ping_via_interface(interface)
                test_results["tests"]["ping"] = ping_test

            # Общий результат
            test_results["overall_success"] = all(
                test.get("accessible", test.get("available", test.get("success", False)))
                for test in test_results["tests"].values()
            )

            return test_results

        except Exception as e:
            logger.error(f"Error testing modem connectivity: {e}")
            return {"error": str(e)}

    async def ping_via_interface(self, interface: str) -> Dict[str, Any]:
        """Ping тест через интерфейс"""
        try:
            result = await asyncio.create_subprocess_exec(
                'ping', '-I', interface, '-c', '3', '-W', '5', '8.8.8.8',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                # Парсим результат ping
                output = stdout.decode()
                loss_match = re.search(r'(\d+)% packet loss', output)
                time_match = re.search(r'time=(\d+\.\d+)ms', output)

                return {
                    "success": True,
                    "packet_loss": int(loss_match.group(1)) if loss_match else 0,
                    "avg_time_ms": float(time_match.group(1)) if time_match else 0,
                    "interface": interface
                }
            else:
                return {
                    "success": False,
                    "error": stderr.decode().strip(),
                    "interface": interface
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "interface": interface
            }

    async def get_modem_web_info(self, modem_id: str) -> Optional[Dict[str, Any]]:
        """Получение информации о модеме через веб-интерфейс"""
        modem = self.modems.get(modem_id)
        if not modem:
            return None

        web_interface = modem.get('web_interface')
        if not web_interface:
            return None

        try:
            # Базовая информация (без авторизации)
            info = {
                "web_interface": web_interface,
                "model": modem.get('model', 'E3372h'),
                "manufacturer": modem.get('manufacturer', 'Huawei'),
                "mac_address": modem.get('mac_address'),
                "interface": modem.get('interface'),
                "subnet_number": modem.get('subnet_number'),
                "accessible": await self.check_web_interface_accessibility(web_interface)
            }

            # Дополнительная информация через API (если доступно)
            # Здесь можно добавить запросы к API модема для получения статуса сигнала,
            # информации о сети и т.д., но это потребует знания API модема

            return info

        except Exception as e:
            logger.error(f"Error getting modem web info: {e}")
            return None

    async def refresh_modem_status(self, modem_id: str) -> bool:
        """Обновление статуса модема"""
        modem = self.modems.get(modem_id)
        if not modem:
            return False

        try:
            # Проверяем доступность веб-интерфейса
            web_interface = modem.get('web_interface')
            if web_interface:
                web_accessible = await self.check_web_interface_accessibility(web_interface)
                modem['web_accessible'] = web_accessible

                # Обновляем статус на основе доступности
                new_status = 'online' if web_accessible else 'offline'
                if modem.get('status') != new_status:
                    await self.update_device_status(modem_id, new_status)

            # Обновляем внешний IP
            external_ip = await self.get_external_ip_via_interface(modem.get('interface_ip'))
            if external_ip:
                modem['external_ip'] = external_ip

            modem['last_seen'] = datetime.now().isoformat()
            return True

        except Exception as e:
            logger.error(f"Error refreshing modem status: {e}")
            return False

    async def get_modem_stats(self, modem_id: str) -> Optional[Dict[str, Any]]:
        """Получение статистики модема"""
        modem = self.modems.get(modem_id)
        if not modem:
            return None

        try:
            stats = {
                "modem_id": modem_id,
                "model": modem.get('model', 'E3372h'),
                "manufacturer": modem.get('manufacturer', 'Huawei'),
                "status": modem.get('status', 'unknown'),
                "interface": modem.get('interface'),
                "web_interface": modem.get('web_interface'),
                "subnet_number": modem.get('subnet_number'),
                "interface_ip": modem.get('interface_ip'),
                "external_ip": modem.get('external_ip'),
                "mac_address": modem.get('mac_address'),
                "last_seen": modem.get('last_seen'),
                "web_accessible": modem.get('web_accessible', False),
                "routing_capable": modem.get('routing_capable', True),
                "connection_status": modem.get('connection_status', 'Unknown'),
                "signal_strength": modem.get('signal_strength', 'N/A'),
                "operator": modem.get('operator', 'Unknown'),
                "technology": modem.get('technology', '4G LTE')
            }

            return stats

        except Exception as e:
            logger.error(f"Error getting modem stats: {e}")
            return None

    async def discover_android_devices(self) -> Dict[str, dict]:
        """Заглушка для совместимости - модемы не поддерживают Android"""
        return {}

    async def get_usb_modem_details(self, device_path: str) -> dict:
        """Заглушка для совместимости - используем веб-интерфейс вместо AT команд"""
        return {}

    async def discover_network_modems(self) -> Dict[str, dict]:
        """Заглушка для совместимости - используем только USB модемы Huawei"""
        return {}
