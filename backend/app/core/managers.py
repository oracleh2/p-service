# backend/app/core/managers.py - ОБНОВЛЕННАЯ ВЕРСИЯ С USB РОТАЦИЕЙ

from typing import Optional, Any, Dict, List

from .dedicated_proxy_manager import DedicatedProxyManager
from .device_manager import DeviceManager
from .modem_manager import ModemManager
from .proxy_server import ProxyServer
from .enhanced_rotation_manager import EnhancedRotationManager
import structlog
import asyncio
from datetime import datetime, timezone, timedelta

logger = structlog.get_logger()

# Глобальные экземпляры менеджеров
_device_manager: Optional[DeviceManager] = None
_modem_manager: Optional[ModemManager] = None
_proxy_server: Optional[ProxyServer] = None
_enhanced_rotation_manager: Optional[EnhancedRotationManager] = None
_stats_collector = None
_managers_initialized = False
_dedicated_proxy_manager: Optional[DedicatedProxyManager] = None


async def init_managers():
    """Инициализация всех менеджеров"""
    global _device_manager, _modem_manager, _proxy_server, _dedicated_proxy_manager, _enhanced_rotation_manager, _managers_initialized

    try:
        if _managers_initialized:
            logger.info("Managers already initialized, skipping...")
            return

        logger.info("Initializing managers with USB rotation support...")

        # Инициализация DeviceManager (Android устройства)
        if _device_manager is None:
            _device_manager = DeviceManager()
            await _device_manager.start()
            logger.info("✅ Device manager (Android) initialized")

        # Инициализация ModemManager (Huawei USB модемы)
        if _modem_manager is None:
            _modem_manager = ModemManager()
            await _modem_manager.start()
            logger.info("✅ Modem manager (Huawei) initialized")

        # Инициализация Enhanced Rotation Manager с поддержкой USB ротации
        if _enhanced_rotation_manager is None:
            _enhanced_rotation_manager = EnhancedRotationManager()
            _enhanced_rotation_manager.device_manager = _device_manager
            _enhanced_rotation_manager.modem_manager = _modem_manager
            await _enhanced_rotation_manager.start()
            logger.info("✅ Enhanced rotation manager initialized with USB reboot support")

        # Инициализация ProxyServer
        if _proxy_server is None:
            _proxy_server = ProxyServer(_device_manager, _stats_collector)
            _proxy_server.modem_manager = _modem_manager
            logger.info("✅ Proxy server initialized")

        # Инициализация DedicatedProxyManager
        if _dedicated_proxy_manager is None:
            _dedicated_proxy_manager = DedicatedProxyManager(_device_manager)
            _dedicated_proxy_manager.modem_manager = _modem_manager
            await _dedicated_proxy_manager.start()
            logger.info("✅ Dedicated proxy manager initialized")

        _managers_initialized = True
        logger.info("✅ All managers initialized successfully with USB rotation support")

    except Exception as e:
        logger.error(f"❌ Error initializing managers: {e}")
        _managers_initialized = False
        raise

# backend/app/core/managers.py - ИСПРАВЛЕННАЯ ВЕРСИЯ ПОЛУЧЕНИЯ МЕТОДОВ РОТАЦИИ

async def _get_usb_modem_rotation_methods(device_id: str, modem_info: dict) -> dict:
    """Получение методов ротации для USB модема E3372h - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    rotation_methods = [
        {
            'method': 'usb_reboot',
            'name': 'USB перезагрузка модема (ЕДИНСТВЕННЫЙ МЕТОД)',
            'description': 'Полная перезагрузка USB модема для смены IP - самый надежный метод для E3372h',
            'recommended': True,
            'risk_level': 'low',
            'effectiveness': 'very_high',
            'explanation': 'Отключает и включает USB устройство на уровне системы, что гарантированно меняет IP',
            'requirements': ['sudo доступ для управления USB устройствами'],
            'time_estimate': '30-45 секунд',
            'success_rate': '95%+'
        }
    ]

    return {
        "device_id": device_id,
        "device_type": "usb_modem",
        "device_mode": "e3372h",
        "available_methods": rotation_methods,
        "current_method": 'usb_reboot',  # ВСЕГДА USB ПЕРЕЗАГРУЗКА
        "device_status": modem_info.get('status', 'unknown'),
        "usb_reboot_info": {
            "title": "USB перезагрузка модема E3372h",
            "description": "Единственный поддерживаемый метод ротации для обеспечения максимальной надежности",
            "why_only_usb": "Для модемов E3372h USB перезагрузка является наиболее надежным методом смены IP",
            "other_methods_disabled": "Другие методы отключены для предотвращения проблем с соединением"
        }
    }

async def perform_device_rotation(device_id: str, method: str = None) -> tuple[bool, str]:
    """ИСПРАВЛЕННАЯ ВЕРСИЯ с принудительным USB методом"""
    rotation_manager = get_enhanced_rotation_manager()
    if not rotation_manager:
        return False, "Enhanced rotation manager not available"

    try:
        logger.info(f"Performing rotation for device: {device_id} with method: {method}")

        # Получаем UUID устройства по его имени из базы данных
        device_uuid = await _get_device_uuid_by_name(device_id)
        if not device_uuid:
            logger.error(f"Device not found in database: {device_id}")
            return False, f"Device not found in database: {device_id}"

        # Для USB модемов ВСЕГДА используем USB перезагрузку
        device_type = await _get_device_type_by_name(device_id)
        if device_type == 'usb_modem':
            method = 'usb_reboot'
            logger.info(f"USB modem detected, forcing USB reboot method for {device_id}")

        # Выполняем ротацию
        success, result = await rotation_manager.rotate_device_ip(str(device_uuid), force_method=method)

        if success:
            logger.info(f"✅ Rotation successful for {device_id} (UUID: {device_uuid}): {result}")
            return True, result
        else:
            logger.error(f"❌ Rotation failed for {device_id} (UUID: {device_uuid}): {result}")
            return False, result

    except Exception as e:
        logger.error(f"Error in device rotation: {e}")
        return False, f"Rotation error: {str(e)}"

def get_device_manager() -> Optional[DeviceManager]:
    """Получение экземпляра DeviceManager (Android устройства)"""
    global _device_manager

    if _device_manager is None:
        logger.info("Creating new DeviceManager instance")
        _device_manager = DeviceManager()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_device_manager.start())
            else:
                asyncio.run(_device_manager.start())
        except Exception as e:
            logger.warning(f"Could not start device manager immediately: {e}")

    return _device_manager


def get_modem_manager() -> Optional[ModemManager]:
    """Получение экземпляра ModemManager (Huawei USB модемы)"""
    global _modem_manager

    if _modem_manager is None:
        logger.info("Creating new ModemManager instance")
        _modem_manager = ModemManager()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_modem_manager.start())
            else:
                asyncio.run(_modem_manager.start())
        except Exception as e:
            logger.warning(f"Could not start modem manager immediately: {e}")

    return _modem_manager


def get_proxy_server() -> Optional[ProxyServer]:
    """Получение экземпляра прокси-сервера"""
    return _proxy_server


def get_dedicated_proxy_manager() -> Optional[DedicatedProxyManager]:
    """Получение экземпляра менеджера индивидуальных прокси"""
    return _dedicated_proxy_manager


def get_enhanced_rotation_manager() -> Optional[EnhancedRotationManager]:
    """Получение экземпляра улучшенного менеджера ротации с поддержкой USB"""
    global _enhanced_rotation_manager

    if _enhanced_rotation_manager is None:
        logger.info("Creating new Enhanced Rotation Manager instance with USB support")
        _enhanced_rotation_manager = EnhancedRotationManager()

        # Связываем с менеджерами устройств если они существуют
        if _device_manager:
            _enhanced_rotation_manager.device_manager = _device_manager
        if _modem_manager:
            _enhanced_rotation_manager.modem_manager = _modem_manager

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_enhanced_rotation_manager.start())
            else:
                asyncio.run(_enhanced_rotation_manager.start())
        except Exception as e:
            logger.warning(f"Could not start enhanced rotation manager immediately: {e}")

    return _enhanced_rotation_manager


# Алиасы для совместимости со старым API
def get_rotation_manager():
    """Алиас для get_enhanced_rotation_manager() для совместимости"""
    return get_enhanced_rotation_manager()


def set_rotation_manager(rotation_manager):
    """Установка экземпляра менеджера ротации (deprecated)"""
    global _enhanced_rotation_manager
    logger.warning("set_rotation_manager is deprecated, use get_enhanced_rotation_manager() instead")
    _enhanced_rotation_manager = rotation_manager


async def cleanup_managers():
    """Очистка всех менеджеров при завершении работы"""
    global _device_manager, _modem_manager, _proxy_server, _dedicated_proxy_manager, _enhanced_rotation_manager

    try:
        if _proxy_server:
            await _proxy_server.stop()
            _proxy_server = None
            logger.info("✅ Proxy server stopped")

        if _enhanced_rotation_manager:
            await _enhanced_rotation_manager.stop()
            _enhanced_rotation_manager = None
            logger.info("✅ Enhanced rotation manager stopped")

        if _device_manager:
            await _device_manager.stop()
            _device_manager = None
            logger.info("✅ Device manager stopped")

        if _modem_manager:
            await _modem_manager.stop()
            _modem_manager = None
            logger.info("✅ Modem manager stopped")

        if _dedicated_proxy_manager:
            await _dedicated_proxy_manager.stop()
            _dedicated_proxy_manager = None
            logger.info("✅ Dedicated proxy manager stopped")

    except Exception as e:
        logger.error(f"❌ Error cleaning up managers: {e}")


async def _get_device_uuid_by_name(device_name: str) -> Optional[str]:
    """Получение UUID устройства по его имени из базы данных"""
    try:
        from ..models.database import AsyncSessionLocal
        from ..models.base import ProxyDevice
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            stmt = select(ProxyDevice.id).where(ProxyDevice.name == device_name)
            result = await db.execute(stmt)
            device_uuid = result.scalar_one_or_none()

            if device_uuid:
                return str(device_uuid)
            else:
                logger.warning(f"Device not found in database: {device_name}")
                return None

    except Exception as e:
        logger.error(f"Error getting device UUID by name: {e}")
        return None


async def _get_device_type_by_name(device_name: str) -> Optional[str]:
    """Получение типа устройства по его имени из базы данных"""
    try:
        from ..models.database import AsyncSessionLocal
        from ..models.base import ProxyDevice
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            stmt = select(ProxyDevice.device_type).where(ProxyDevice.name == device_name)
            result = await db.execute(stmt)
            device_type = result.scalar_one_or_none()

            if device_type:
                return device_type
            else:
                logger.warning(f"Device type not found in database: {device_name}")
                return None

    except Exception as e:
        logger.error(f"Error getting device type by name: {e}")
        return None


async def get_device_rotation_methods(device_id: str) -> dict:
    """Получение доступных методов ротации для устройства с поддержкой USB"""
    device_manager = get_device_manager()
    modem_manager = get_modem_manager()

    if not device_manager and not modem_manager:
        return {"error": "No device managers available"}

    try:
        # Ищем устройство в DeviceManager
        if device_manager:
            all_devices = await device_manager.get_all_devices()
            if device_id in all_devices:
                device_info = all_devices[device_id]
                return await _get_android_rotation_methods(device_id, device_info)

        # Ищем устройство в ModemManager
        if modem_manager:
            all_modems = await modem_manager.get_all_devices()
            if device_id in all_modems:
                modem_info = all_modems[device_id]
                return await _get_usb_modem_rotation_methods(device_id, modem_info)

        return {"error": "Device not found"}

    except Exception as e:
        logger.error(f"Error getting rotation methods: {e}")
        return {"error": str(e)}


async def _get_android_rotation_methods(device_id: str, device_info: dict) -> dict:
    """Получение методов ротации для Android устройства"""
    rotation_methods = [
        {
            'method': 'data_toggle',
            'name': 'Переключение мобильных данных',
            'description': 'Отключение и включение мобильных данных через ADB команды',
            'recommended': True,
            'risk_level': 'low'
        },
        {
            'method': 'airplane_mode',
            'name': 'Режим полета',
            'description': 'Включение и отключение режима полета',
            'recommended': False,
            'risk_level': 'medium'
        },
        {
            'method': 'usb_reconnect',
            'name': 'Переподключение USB',
            'description': 'Переподключение USB tethering',
            'recommended': False,
            'risk_level': 'medium'
        }
    ]

    return {
        "device_id": device_id,
        "device_type": "android",
        "available_methods": rotation_methods,
        "current_method": device_info.get('rotation_method', 'data_toggle'),
        "device_status": device_info.get('status', 'unknown')
    }


async def test_device_rotation(device_id: str, method: str) -> dict:
    """Тестирование метода ротации устройства с поддержкой USB"""
    device_manager = get_device_manager()
    modem_manager = get_modem_manager()

    if not device_manager and not modem_manager:
        return {"error": "No device managers available"}

    try:
        device_info = None
        device_type = None

        # Ищем устройство в DeviceManager
        if device_manager:
            all_devices = await device_manager.get_all_devices()
            if device_id in all_devices:
                device_info = all_devices[device_id]
                device_type = "android"

        # Ищем устройство в ModemManager
        if not device_info and modem_manager:
            all_modems = await modem_manager.get_all_devices()
            if device_id in all_modems:
                device_info = all_modems[device_id]
                device_type = "usb_modem"

        if not device_info:
            return {"error": "Device not found"}

        # Получаем UUID устройства
        device_uuid = await _get_device_uuid_by_name(device_id)
        if not device_uuid:
            return {"error": "Device not found in database"}

        # Для USB модемов принудительно используем USB перезагрузку
        if device_type == "usb_modem":
            method = "usb_reboot"
            logger.info(f"Testing USB reboot method for device {device_id}")

        # Получаем текущий IP
        current_ip = None
        if device_type == "android" and device_manager:
            current_ip = await device_manager.get_device_external_ip(device_id)
        elif device_type == "usb_modem" and modem_manager:
            current_ip = await modem_manager.get_device_external_ip(device_id)

        # Выполняем тестовую ротацию
        import time
        start_time = time.time()

        logger.info(f"Testing rotation method '{method}' for device {device_id} (UUID: {device_uuid})")

        # Используем perform_device_rotation для тестирования
        success, result = await perform_device_rotation(device_id, method)
        execution_time = time.time() - start_time

        # Ждем стабилизации
        await asyncio.sleep(10)

        # Проверяем новый IP
        new_ip = None
        if device_type == "android" and device_manager:
            new_ip = await device_manager.get_device_external_ip(device_id)
        elif device_type == "usb_modem" and modem_manager:
            new_ip = await modem_manager.get_device_external_ip(device_id)

        ip_changed = new_ip != current_ip if current_ip and new_ip else False

        return {
            "success": success,
            "method": method,
            "device_id": device_id,
            "device_uuid": device_uuid,
            "device_type": device_type,
            "execution_time_seconds": round(execution_time, 2),
            "current_ip_before": current_ip,
            "new_ip_after": new_ip,
            "ip_changed": ip_changed,
            "result_message": result if success else f"Test rotation failed: {result}",
            "timestamp": datetime.now().isoformat(),
            "recommendation": "success" if success and ip_changed else "method_working_ip_unchanged" if success else "try_different_method",
            "usb_reboot_note": "USB reboot method used for reliable IP rotation" if device_type == "usb_modem" else None
        }

    except Exception as e:
        logger.error(f"Error testing rotation: {e}")
        return {"error": str(e)}


async def get_all_devices_combined() -> Dict[str, dict]:
    """Получение всех устройств из обоих менеджеров"""
    combined_devices = {}

    try:
        # Получаем Android устройства
        device_manager = get_device_manager()
        if device_manager:
            android_devices = await device_manager.get_all_devices()
            combined_devices.update(android_devices)

        # Получаем USB модемы
        modem_manager = get_modem_manager()
        if modem_manager:
            usb_modems = await modem_manager.get_all_devices()
            combined_devices.update(usb_modems)

    except Exception as e:
        logger.error(f"Error getting combined devices: {e}")

    return combined_devices


async def get_online_devices_combined() -> List[dict]:
    """Получение всех онлайн устройств из обоих менеджеров"""
    online_devices = []

    try:
        # Получаем онлайн Android устройства
        device_manager = get_device_manager()
        if device_manager:
            android_devices = await device_manager.get_available_devices()
            online_devices.extend(android_devices)

        # Получаем онлайн USB модемы
        modem_manager = get_modem_manager()
        if modem_manager:
            usb_modems = await modem_manager.get_available_devices()
            online_devices.extend(usb_modems)

    except Exception as e:
        logger.error(f"Error getting online devices: {e}")

    return online_devices


async def get_random_device_combined() -> Optional[dict]:
    """Получение случайного онлайн устройства из обоих менеджеров"""
    online_devices = await get_online_devices_combined()

    if not online_devices:
        return None

    import random
    return random.choice(online_devices)


async def get_device_by_id_combined(device_id: str) -> Optional[dict]:
    """Получение устройства по ID из любого менеджера"""
    try:
        # Ищем в DeviceManager
        device_manager = get_device_manager()
        if device_manager:
            device = await device_manager.get_device_by_id(device_id)
            if device:
                return device

        # Ищем в ModemManager
        modem_manager = get_modem_manager()
        if modem_manager:
            device = await modem_manager.get_device_by_id(device_id)
            if device:
                return device

    except Exception as e:
        logger.error(f"Error getting device by ID: {e}")

    return None


async def get_devices_summary_combined() -> Dict[str, Any]:
    """Получение сводной информации о всех устройствах"""
    try:
        summary = {
            "android_devices": {"total": 0, "online": 0, "offline": 0},
            "usb_modems": {"total": 0, "online": 0, "offline": 0},
            "total_devices": 0,
            "total_online": 0,
            "total_offline": 0,
            "last_update": datetime.now().isoformat()
        }

        # Статистика Android устройств
        device_manager = get_device_manager()
        if device_manager:
            android_summary = await device_manager.get_summary()
            summary["android_devices"] = {
                "total": android_summary.get("total_devices", 0),
                "online": android_summary.get("online_devices", 0),
                "offline": android_summary.get("offline_devices", 0)
            }

        # Статистика USB модемов
        modem_manager = get_modem_manager()
        if modem_manager:
            modem_summary = await modem_manager.get_summary()
            summary["usb_modems"] = {
                "total": modem_summary.get("total_devices", 0),
                "online": modem_summary.get("online_devices", 0),
                "offline": modem_summary.get("offline_devices", 0)
            }

        # Общая статистика
        summary["total_devices"] = summary["android_devices"]["total"] + summary["usb_modems"]["total"]
        summary["total_online"] = summary["android_devices"]["online"] + summary["usb_modems"]["online"]
        summary["total_offline"] = summary["android_devices"]["offline"] + summary["usb_modems"]["offline"]

        return summary

    except Exception as e:
        logger.error(f"Error getting devices summary: {e}")
        return {
            "android_devices": {"total": 0, "online": 0, "offline": 0},
            "usb_modems": {"total": 0, "online": 0, "offline": 0},
            "total_devices": 0,
            "total_online": 0,
            "total_offline": 0,
            "error": str(e)
        }


async def get_device_uuid_by_name(device_name: str) -> Optional[str]:
    """Получение UUID устройства по его имени из базы данных"""
    try:
        from ..models.database import AsyncSessionLocal
        from ..models.base import ProxyDevice
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            stmt = select(ProxyDevice.id).where(ProxyDevice.name == device_name)
            result = await db.execute(stmt)
            device_uuid = result.scalar_one_or_none()

            if device_uuid:
                return str(device_uuid)
            else:
                logger.warning(f"Device not found in database: {device_name}")
                return None

    except Exception as e:
        logger.error(f"Error getting device UUID by name: {e}")
        return None


async def get_device_name_by_uuid(device_uuid: str) -> Optional[str]:
    """Получение имени устройства по его UUID из базы данных"""
    try:
        from ..models.database import AsyncSessionLocal
        from ..models.base import ProxyDevice
        from sqlalchemy import select
        import uuid

        async with AsyncSessionLocal() as db:
            stmt = select(ProxyDevice.name).where(ProxyDevice.id == uuid.UUID(device_uuid))
            result = await db.execute(stmt)
            device_name = result.scalar_one_or_none()

            if device_name:
                return device_name
            else:
                logger.warning(f"Device not found in database by UUID: {device_uuid}")
                return None

    except Exception as e:
        logger.error(f"Error getting device name by UUID: {e}")
        return None


async def get_device_by_id_combined_with_uuid(device_id: str) -> Optional[dict]:
    """Получение устройства по ID из любого менеджера с добавлением UUID"""
    try:
        # Получаем базовую информацию об устройстве
        device_info = await get_device_by_id_combined(device_id)

        if device_info:
            # Добавляем UUID к информации об устройстве
            device_uuid = await get_device_uuid_by_name(device_id)
            if device_uuid:
                device_info['uuid'] = device_uuid
                device_info['database_id'] = device_uuid

        return device_info

    except Exception as e:
        logger.error(f"Error getting device by ID with UUID: {e}")
        return None


async def sync_device_managers_with_database():
    """Синхронизация данных из менеджеров устройств с базой данных"""
    try:
        from ..models.database import AsyncSessionLocal
        from ..models.base import ProxyDevice
        from sqlalchemy import select, update

        logger.info("Starting device managers sync with database...")

        # Получаем все устройства из менеджеров
        all_devices = await get_all_devices_combined()

        # Синхронизируем с базой данных
        async with AsyncSessionLocal() as db:
            for device_name, device_info in all_devices.items():
                # Проверяем, есть ли устройство в БД
                stmt = select(ProxyDevice).where(ProxyDevice.name == device_name)
                result = await db.execute(stmt)
                db_device = result.scalar_one_or_none()

                if db_device:
                    # Обновляем статус и внешний IP
                    update_data = {
                        'status': device_info.get('status', 'unknown'),
                        'last_heartbeat': datetime.now()
                    }

                    # Обновляем внешний IP если есть
                    external_ip = device_info.get('external_ip')
                    if external_ip:
                        update_data['current_external_ip'] = external_ip

                    stmt = update(ProxyDevice).where(
                        ProxyDevice.name == device_name
                    ).values(**update_data)

                    await db.execute(stmt)
                    logger.debug(f"Updated device {device_name} in database")
                else:
                    logger.warning(f"Device {device_name} found in managers but not in database")

            await db.commit()
            logger.info("✅ Device managers sync completed")

    except Exception as e:
        logger.error(f"Error syncing device managers with database: {e}")


async def get_all_devices_with_uuid() -> Dict[str, dict]:
    """Получение всех устройств из обоих менеджеров с добавлением UUID"""
    try:
        # Получаем все устройства
        all_devices = await get_all_devices_combined()

        # Добавляем UUID к каждому устройству
        for device_name, device_info in all_devices.items():
            device_uuid = await get_device_uuid_by_name(device_name)
            if device_uuid:
                device_info['uuid'] = device_uuid
                device_info['database_id'] = device_uuid

        return all_devices

    except Exception as e:
        logger.error(f"Error getting all devices with UUID: {e}")
        return {}


async def perform_device_rotation_by_uuid(device_uuid: str, method: str = None) -> tuple[bool, str]:
    """Выполнение ротации устройства по UUID с поддержкой USB перезагрузки"""
    rotation_manager = get_enhanced_rotation_manager()
    if not rotation_manager:
        return False, "Enhanced rotation manager not available"

    try:
        logger.info(f"Performing rotation for device UUID: {device_uuid} with method: {method}")

        # Для USB модемов принудительно используем USB перезагрузку
        device_type = await _get_device_type_by_uuid(device_uuid)
        if device_type == 'usb_modem':
            logger.info(f"USB modem detected, forcing USB reboot method for UUID {device_uuid}")
            method = 'usb_reboot'

        # Выполняем ротацию
        success, result = await rotation_manager.rotate_device_ip(device_uuid, force_method=method)

        if success:
            logger.info(f"✅ Rotation successful for UUID {device_uuid}: {result}")
            return True, result
        else:
            logger.error(f"❌ Rotation failed for UUID {device_uuid}: {result}")
            return False, result

    except Exception as e:
        logger.error(f"Error in device rotation by UUID: {e}")
        return False, f"Rotation error: {str(e)}"


async def _get_device_type_by_uuid(device_uuid: str) -> Optional[str]:
    """Получение типа устройства по его UUID из базы данных"""
    try:
        from ..models.database import AsyncSessionLocal
        from ..models.base import ProxyDevice
        from sqlalchemy import select
        import uuid

        async with AsyncSessionLocal() as db:
            stmt = select(ProxyDevice.device_type).where(ProxyDevice.id == uuid.UUID(device_uuid))
            result = await db.execute(stmt)
            device_type = result.scalar_one_or_none()

            if device_type:
                return device_type
            else:
                logger.warning(f"Device type not found in database by UUID: {device_uuid}")
                return None

    except Exception as e:
        logger.error(f"Error getting device type by UUID: {e}")
        return None


async def get_device_rotation_methods_by_uuid(device_uuid: str) -> dict:
    """Получение доступных методов ротации для устройства по UUID"""
    try:
        # Получаем имя устройства по UUID
        device_name = await get_device_name_by_uuid(device_uuid)
        if not device_name:
            return {"error": "Device not found by UUID"}

        # Получаем методы ротации через имя устройства
        return await get_device_rotation_methods(device_name)

    except Exception as e:
        logger.error(f"Error getting rotation methods by UUID: {e}")
        return {"error": str(e)}


async def test_device_rotation_by_uuid(device_uuid: str, method: str) -> dict:
    """Тестирование метода ротации устройства по UUID"""
    try:
        # Получаем имя устройства по UUID
        device_name = await get_device_name_by_uuid(device_uuid)
        if not device_name:
            return {"error": "Device not found by UUID"}

        # Для USB модемов принудительно используем USB перезагрузку
        device_type = await _get_device_type_by_uuid(device_uuid)
        if device_type == 'usb_modem':
            method = 'usb_reboot'
            logger.info(f"USB modem detected, forcing USB reboot method for UUID {device_uuid}")

        # Выполняем тест через имя устройства
        result = await test_device_rotation(device_name, method)

        # Добавляем UUID к результату
        if isinstance(result, dict) and 'error' not in result:
            result['device_uuid'] = device_uuid

        return result

    except Exception as e:
        logger.error(f"Error testing rotation by UUID: {e}")
        return {"error": str(e)}


async def get_usb_rotation_diagnostics() -> dict:
    """Получение диагностической информации о USB ротации"""
    try:
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "usb_rotation_status": "enabled",
            "supported_devices": ["Huawei E3372h"],
            "rotation_method": "usb_reboot",
            "system_requirements": {
                "sudo_access": "required",
                "usb_sysfs_access": "required",
                "lsusb_command": "required",
                "curl_command": "required"
            },
            "diagnostics": {}
        }

        # Проверяем доступность sudo
        try:
            result = await asyncio.create_subprocess_exec(
                'sudo', '-n', 'true',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            diagnostics["diagnostics"]["sudo_access"] = result.returncode == 0
        except Exception:
            diagnostics["diagnostics"]["sudo_access"] = False

        # Проверяем доступность lsusb
        try:
            result = await asyncio.create_subprocess_exec(
                'lsusb',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            diagnostics["diagnostics"]["lsusb_available"] = result.returncode == 0
        except Exception:
            diagnostics["diagnostics"]["lsusb_available"] = False

        # Проверяем наличие USB устройств Huawei
        try:
            result = await asyncio.create_subprocess_exec(
                'lsusb',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                lsusb_output = stdout.decode()
                huawei_devices = [line for line in lsusb_output.split('\n') if '12d1' in line and 'Huawei' in line]
                diagnostics["diagnostics"]["huawei_devices_found"] = len(huawei_devices)
                diagnostics["diagnostics"]["huawei_devices"] = huawei_devices
            else:
                diagnostics["diagnostics"]["huawei_devices_found"] = 0
                diagnostics["diagnostics"]["huawei_devices"] = []
        except Exception:
            diagnostics["diagnostics"]["huawei_devices_found"] = 0
            diagnostics["diagnostics"]["huawei_devices"] = []

        # Проверяем доступность curl
        try:
            result = await asyncio.create_subprocess_exec(
                'curl', '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            diagnostics["diagnostics"]["curl_available"] = result.returncode == 0
        except Exception:
            diagnostics["diagnostics"]["curl_available"] = False

        # Проверяем доступность /sys/bus/usb/devices
        try:
            result = await asyncio.create_subprocess_exec(
                'test', '-d', '/sys/bus/usb/devices',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            diagnostics["diagnostics"]["usb_sysfs_available"] = result.returncode == 0
        except Exception:
            diagnostics["diagnostics"]["usb_sysfs_available"] = False

        # Общая готовность системы
        required_checks = [
            "sudo_access",
            "lsusb_available",
            "curl_available",
            "usb_sysfs_available"
        ]

        ready_checks = sum(1 for check in required_checks if diagnostics["diagnostics"].get(check, False))
        diagnostics["system_readiness"] = {
            "ready_checks": ready_checks,
            "total_checks": len(required_checks),
            "percentage": (ready_checks / len(required_checks)) * 100,
            "is_ready": ready_checks == len(required_checks)
        }

        return diagnostics

    except Exception as e:
        logger.error(f"Error getting USB rotation diagnostics: {e}")
        return {"error": str(e)}


async def test_usb_rotation_capability() -> dict:
    """Тестирование возможности USB ротации в системе"""
    try:
        test_results = {
            "timestamp": datetime.now().isoformat(),
            "test_type": "usb_rotation_capability",
            "results": {}
        }

        # Тест 1: Поиск USB устройств Huawei
        logger.info("Testing USB device discovery...")
        try:
            result = await asyncio.create_subprocess_exec(
                'lsusb',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                lsusb_output = stdout.decode()
                huawei_devices = [line for line in lsusb_output.split('\n') if '12d1' in line]
                test_results["results"]["device_discovery"] = {
                    "success": len(huawei_devices) > 0,
                    "devices_found": len(huawei_devices),
                    "devices": huawei_devices
                }
            else:
                test_results["results"]["device_discovery"] = {
                    "success": False,
                    "error": stderr.decode()
                }
        except Exception as e:
            test_results["results"]["device_discovery"] = {
                "success": False,
                "error": str(e)
            }

        # Тест 2: Проверка доступа к sysfs
        logger.info("Testing sysfs access...")
        try:
            result = await asyncio.create_subprocess_exec(
                'find', '/sys/bus/usb/devices/', '-name', 'idVendor', '-exec', 'grep', '-l', '12d1', '{}', ';',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                vendor_files = [f for f in stdout.decode().split('\n') if f]
                test_results["results"]["sysfs_access"] = {
                    "success": len(vendor_files) > 0,
                    "huawei_devices_in_sysfs": len(vendor_files),
                    "vendor_files": vendor_files
                }
            else:
                test_results["results"]["sysfs_access"] = {
                    "success": False,
                    "error": stderr.decode()
                }
        except Exception as e:
            test_results["results"]["sysfs_access"] = {
                "success": False,
                "error": str(e)
            }

        # Тест 3: Проверка sudo доступа
        logger.info("Testing sudo access...")
        try:
            result = await asyncio.create_subprocess_exec(
                'sudo', '-n', 'echo', 'test',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            test_results["results"]["sudo_access"] = {
                "success": result.returncode == 0,
                "message": "sudo access available" if result.returncode == 0 else "sudo access required"
            }
        except Exception as e:
            test_results["results"]["sudo_access"] = {
                "success": False,
                "error": str(e)
            }

        # Общий результат
        all_tests = list(test_results["results"].values())
        successful_tests = sum(1 for test in all_tests if test.get("success", False))

        test_results["summary"] = {
            "total_tests": len(all_tests),
            "successful_tests": successful_tests,
            "success_rate": (successful_tests / len(all_tests)) * 100,
            "overall_ready": successful_tests == len(all_tests)
        }

        return test_results

    except Exception as e:
        logger.error(f"Error testing USB rotation capability: {e}")
        return {"error": str(e)}
