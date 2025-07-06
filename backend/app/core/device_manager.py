import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import uuid

from ..database import AsyncSessionLocal, get_system_config
from ..models.base import ProxyDevice, RotationConfig, IpHistory
from ..config import settings

logger = structlog.get_logger()


class DeviceManager:
    """Менеджер для управления мобильными устройствами"""

    def __init__(self):
        self.devices: Dict[str, dict] = {}
        self.running = False
        self.monitor_task = None
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        """Запуск менеджера устройств"""
        self.running = True
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100)
        )

        # Загрузка устройств из БД
        await self.load_devices()

        # Запуск мониторинга
        self.monitor_task = asyncio.create_task(self.monitor_devices())

        logger.info("Device manager started")

    async def stop(self):
        """Остановка менеджера устройств"""
        self.running = False

        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        if self.session:
            await self.session.close()

        logger.info("Device manager stopped")

    def is_running(self) -> bool:
        """Проверка запущен ли менеджер"""
        return self.running

    async def load_devices(self):
        """Загрузка устройств из базы данных"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProxyDevice).where(ProxyDevice.status != 'maintenance')
                result = await db.execute(stmt)
                devices = result.scalars().all()

                for device in devices:
                    self.devices[str(device.id)] = {
                        'id': str(device.id),
                        'name': device.name,
                        'device_type': device.device_type,
                        'ip_address': device.ip_address,
                        'port': device.port,
                        'status': device.status,
                        'current_external_ip': device.current_external_ip,
                        'operator': device.operator,
                        'region': device.region,
                        'last_heartbeat': device.last_heartbeat,
                        'last_ip_rotation': device.last_ip_rotation,
                        'rotation_interval': device.rotation_interval,
                        'total_requests': device.total_requests,
                        'successful_requests': device.successful_requests,
                        'failed_requests': device.failed_requests,
                        'avg_response_time_ms': device.avg_response_time_ms,
                        'is_available': False,
                        'last_check': None
                    }

                logger.info(f"Loaded {len(self.devices)} devices from database")

        except Exception as e:
            logger.error("Failed to load devices from database", error=str(e))

    async def monitor_devices(self):
        """Мониторинг состояния устройств"""
        while self.running:
            try:
                await self.check_devices_health()
                await asyncio.sleep(30)  # Проверка каждые 30 секунд
            except Exception as e:
                logger.error("Error in device monitoring", error=str(e))
                await asyncio.sleep(5)

    async def check_devices_health(self):
        """Проверка здоровья всех устройств"""
        if not self.devices:
            return

        tasks = []
        for device_id in self.devices.keys():
            task = asyncio.create_task(self.check_device_health(device_id))
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def check_device_health(self, device_id: str):
        """Проверка здоровья конкретного устройства"""
        try:
            device = self.devices.get(device_id)
            if not device:
                return

            # Проверка доступности через HTTP
            is_available = await self.ping_device(device)

            # Обновление статуса в памяти
            device['is_available'] = is_available
            device['last_check'] = datetime.now(timezone.utc)

            # Определение нового статуса
            new_status = 'online' if is_available else 'offline'

            # Проверка heartbeat timeout
            heartbeat_timeout = await get_system_config('heartbeat_timeout', 60)
            if device['last_heartbeat']:
                time_since_heartbeat = (datetime.now(timezone.utc) - device['last_heartbeat']).total_seconds()
                if time_since_heartbeat > heartbeat_timeout:
                    new_status = 'offline'

            # Обновление статуса в БД если изменился
            if device['status'] != new_status:
                await self.update_device_status(device_id, new_status)
                device['status'] = new_status

                logger.info(
                    "Device status changed",
                    device_id=device_id,
                    device_name=device['name'],
                    old_status=device['status'],
                    new_status=new_status
                )

        except Exception as e:
            logger.error(f"Failed to check device health", device_id=device_id, error=str(e))

    async def ping_device(self, device: dict) -> bool:
        """Проверка доступности устройства"""
        try:
            url = f"http://{device['ip_address']}:{device['port']}/health"

            async with self.session.get(url, timeout=5) as response:
                return response.status == 200

        except Exception:
            return False

    async def update_device_status(self, device_id: str, status: str):
        """Обновление статуса устройства в БД"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == uuid.UUID(device_id)
                ).values(
                    status=status,
                    updated_at=datetime.now(timezone.utc)
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error("Failed to update device status", device_id=device_id, error=str(e))

    async def get_available_devices(self) -> List[dict]:
        """Получение списка доступных устройств"""
        return [
            device for device in self.devices.values()
            if device['status'] == 'online' and device['is_available']
        ]

    async def get_device_by_id(self, device_id: str) -> Optional[dict]:
        """Получение устройства по ID"""
        return self.devices.get(device_id)

    async def get_random_device(self) -> Optional[dict]:
        """Получение случайного доступного устройства"""
        import random

        available_devices = await self.get_available_devices()
        if available_devices:
            return random.choice(available_devices)
        return None

    async def get_device_by_operator(self, operator: str) -> Optional[dict]:
        """Получение устройства по оператору"""
        import random

        available_devices = await self.get_available_devices()
        operator_devices = [
            device for device in available_devices
            if device['operator'] and device['operator'].lower() == operator.lower()
        ]

        if operator_devices:
            return random.choice(operator_devices)
        return None

    async def get_device_by_region(self, region: str) -> Optional[dict]:
        """Получение устройства по региону"""
        import random

        available_devices = await self.get_available_devices()
        region_devices = [
            device for device in available_devices
            if device['region'] and device['region'].lower() == region.lower()
        ]

        if region_devices:
            return random.choice(region_devices)
        return None

    async def add_device(self, device_data: dict):
        """Добавление нового устройства"""
        device_id = device_data['id']
        self.devices[device_id] = {
            **device_data,
            'is_available': False,
            'last_check': None
        }

        logger.info("Device added to manager", device_id=device_id, device_name=device_data['name'])

    async def remove_device(self, device_id: str):
        """Удаление устройства"""
        if device_id in self.devices:
            device_name = self.devices[device_id]['name']
            del self.devices[device_id]
            logger.info("Device removed from manager", device_id=device_id, device_name=device_name)

    async def update_device(self, device_id: str, device_data: dict):
        """Обновление данных устройства"""
        if device_id in self.devices:
            self.devices[device_id].update(device_data)
            logger.info("Device updated in manager", device_id=device_id)

    async def get_summary(self) -> dict:
        """Получение общей статистики устройств"""
        total_devices = len(self.devices)
        online_devices = len([d for d in self.devices.values() if d['status'] == 'online'])
        offline_devices = len([d for d in self.devices.values() if d['status'] == 'offline'])
        busy_devices = len([d for d in self.devices.values() if d['status'] == 'busy'])
        maintenance_devices = len([d for d in self.devices.values() if d['status'] == 'maintenance'])

        return {
            'total_devices': total_devices,
            'online_devices': online_devices,
            'offline_devices': offline_devices,
            'busy_devices': busy_devices,
            'maintenance_devices': maintenance_devices,
            'available_devices': len(await self.get_available_devices())
        }

    async def update_device_stats(self, device_id: str, response_time: int, success: bool):
        """Обновление статистики устройства"""
        if device_id not in self.devices:
            return

        device = self.devices[device_id]
        device['total_requests'] += 1

        if success:
            device['successful_requests'] += 1
        else:
            device['failed_requests'] += 1

        # Обновление среднего времени ответа
        if device['total_requests'] > 1:
            device['avg_response_time_ms'] = (
                    (device['avg_response_time_ms'] * (device['total_requests'] - 1) + response_time)
                    / device['total_requests']
            )
        else:
            device['avg_response_time_ms'] = response_time

        # Периодическое обновление в БД (каждые 10 запросов)
        if device['total_requests'] % 10 == 0:
            await self.sync_device_stats_to_db(device_id)

    async def sync_device_stats_to_db(self, device_id: str):
        """Синхронизация статистики устройства с БД"""
        try:
            device = self.devices.get(device_id)
            if not device:
                return

            async with AsyncSessionLocal() as db:
                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == uuid.UUID(device_id)
                ).values(
                    total_requests=device['total_requests'],
                    successful_requests=device['successful_requests'],
                    failed_requests=device['failed_requests'],
                    avg_response_time_ms=int(device['avg_response_time_ms']),
                    updated_at=datetime.now(timezone.utc)
                )
                await db.execute(stmt)
                await db.commit()

        except Exception as e:
            logger.error("Failed to sync device stats to DB", device_id=device_id, error=str(e))

    async def restart_device(self, device_id: str) -> bool:
        """Перезапуск устройства"""
        try:
            device = self.devices.get(device_id)
            if not device:
                return False

            # Отправка команды перезапуска на устройство
            url = f"http://{device['ip_address']}:{device['port']}/restart"

            async with self.session.post(url, timeout=10) as response:
                if response.status == 200:
                    # Обновление статуса
                    await self.update_device_status(device_id, 'offline')
                    device['status'] = 'offline'

                    logger.info("Device restart initiated", device_id=device_id)
                    return True
                else:
                    logger.error("Failed to restart device", device_id=device_id, status=response.status)
                    return False

        except Exception as e:
            logger.error("Error restarting device", device_id=device_id, error=str(e))
            return False

    async def get_device_external_ip(self, device_id: str) -> Optional[str]:
        """Получение внешнего IP устройства"""
        try:
            device = self.devices.get(device_id)
            if not device:
                return None

            # Запрос внешнего IP через устройство
            url = f"http://{device['ip_address']}:{device['port']}/external-ip"

            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    external_ip = data.get('external_ip')

                    if external_ip:
                        # Обновление IP в памяти и БД
                        device['current_external_ip'] = external_ip
                        await self.update_device_external_ip(device_id, external_ip)

                        return external_ip

            return None

        except Exception as e:
            logger.error("Error getting device external IP", device_id=device_id, error=str(e))
            return None

    async def update_device_external_ip(self, device_id: str, external_ip: str):
        """Обновление внешнего IP устройства в БД"""
        try:
            async with AsyncSessionLocal() as db:
                stmt = update(ProxyDevice).where(
                    ProxyDevice.id == uuid.UUID(device_id)
                ).values(
                    current_external_ip=external_ip,
                    updated_at=datetime.now(timezone.utc)
                )
                await db.execute(stmt)
                await db.commit()

                # Добавление в историю IP
                await self.add_ip_to_history(device_id, external_ip)

        except Exception as e:
            logger.error("Failed to update device external IP", device_id=device_id, error=str(e))

    async def add_ip_to_history(self, device_id: str, ip_address: str):
        """Добавление IP в историю"""
        try:
            device = self.devices.get(device_id)
            if not device:
                return

            async with AsyncSessionLocal() as db:
                # Проверка существования IP в истории
                stmt = select(IpHistory).where(
                    IpHistory.device_id == uuid.UUID(device_id),
                    IpHistory.ip_address == ip_address
                )
                result = await db.execute(stmt)
                ip_history = result.scalar_one_or_none()

                if ip_history:
                    # Обновление времени последнего использования
                    ip_history.last_seen = datetime.now(timezone.utc)
                    ip_history.total_requests += 1
                else:
                    # Создание новой записи
                    ip_history = IpHistory(
                        device_id=uuid.UUID(device_id),
                        ip_address=ip_address,
                        operator=device['operator'],
                        total_requests=1
                    )
                    db.add(ip_history)

                await db.commit()

        except Exception as e:
            logger.error("Failed to add IP to history", device_id=device_id, error=str(e))

    async def get_devices_by_status(self, status: str) -> List[dict]:
        """Получение устройств по статусу"""
        return [
            device for device in self.devices.values()
            if device['status'] == status
        ]

    async def set_device_maintenance(self, device_id: str, maintenance: bool):
        """Установка/снятие режима обслуживания"""
        if device_id in self.devices:
            status = 'maintenance' if maintenance else 'offline'
            await self.update_device_status(device_id, status)
            self.devices[device_id]['status'] = status

            logger.info(
                "Device maintenance mode changed",
                device_id=device_id,
                maintenance=maintenance
            )