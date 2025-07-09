# backend/app/core/managers.py - ОБНОВЛЕННАЯ ВЕРСИЯ С ДВУМЯ МЕНЕДЖЕРАМИ

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

        logger.info("Initializing managers...")

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

        # Инициализация Enhanced Rotation Manager
        if _enhanced_rotation_manager is None:
            _enhanced_rotation_manager = EnhancedRotationManager()
            _enhanced_rotation_manager.device_manager = _device_manager
            _enhanced_rotation_manager.modem_manager = _modem_manager
            await _enhanced_rotation_manager.start()
            logger.info("✅ Enhanced rotation manager initialized")

        # Инициализация ProxyServer
        if _proxy_server is None:
            _proxy_server = ProxyServer(_device_manager, _stats_collector)
            _proxy_server.modem_manager = _modem_manager  # Добавляем поддержку модемов
            logger.info("✅ Proxy server initialized")

        # Инициализация DedicatedProxyManager
        if _dedicated_proxy_manager is None:
            _dedicated_proxy_manager = DedicatedProxyManager(_device_manager)
            _dedicated_proxy_manager.modem_manager = _modem_manager  # Добавляем поддержку модемов
            await _dedicated_proxy_manager.start()
            logger.info("✅ Dedicated proxy manager initialized")

        _managers_initialized = True
        logger.info("✅ All managers initialized successfully")

    except Exception as e:
        logger.error(f"❌ Error initializing managers: {e}")
        _managers_initialized = False
        raise


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
    """Получение экземпляра улучшенного менеджера ротации"""
    global _enhanced_rotation_manager

    if _enhanced_rotation_manager is None:
        logger.info("Creating new Enhanced Rotation Manager instance")
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


async def perform_device_rotation(device_id: str, method: str = None) -> tuple[bool, str]:
    """
    Выполнение ротации устройства с использованием EnhancedRotationManager

    Args:
        device_id: ID устройства (строковый ID из DeviceManager или ModemManager)
        method: Принудительный метод ротации

    Returns:
        tuple[bool, str]: (успех, сообщение/новый_IP)
    """
    rotation_manager = get_enhanced_rotation_manager()
    if not rotation_manager:
        return False, "Enhanced rotation manager not available"

    try:
        logger.info(f"Performing rotation for device: {device_id} with method: {method}")

        # Используем EnhancedRotationManager для ротации
        success, result = await rotation_manager.rotate_device_ip(device_id)

        if success:
            logger.info(f"✅ Rotation successful for {device_id}: {result}")
            return True, result
        else:
            logger.error(f"❌ Rotation failed for {device_id}: {result}")
            return False, result

    except Exception as e:
        logger.error(f"Error in device rotation: {e}")
        return False, f"Rotation error: {str(e)}"


async def get_device_rotation_methods(device_id: str) -> dict:
    """Получение доступных методов ротации для устройства"""
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
                return await _get_modem_rotation_methods(device_id, modem_info)

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


async def _get_modem_rotation_methods(device_id: str, modem_info: dict) -> dict:
    """Получение методов ротации для USB модема"""
    rotation_methods = [
        {
            'method': 'web_interface',
            'name': 'Веб-интерфейс',
            'description': 'Перезагрузка через веб-интерфейс модема',
            'recommended': True,
            'risk_level': 'low'
        },
        {
            'method': 'interface_restart',
            'name': 'Перезапуск интерфейса',
            'description': 'Перезапуск сетевого интерфейса модема',
            'recommended': False,
            'risk_level': 'medium'
        },
        {
            'method': 'dhcp_renew',
            'name': 'Обновление DHCP',
            'description': 'Запрос нового IP через DHCP',
            'recommended': False,
            'risk_level': 'low'
        }
    ]

    return {
        "device_id": device_id,
        "device_type": "usb_modem",
        "available_methods": rotation_methods,
        "current_method": modem_info.get('rotation_method', 'web_interface'),
        "device_status": modem_info.get('status', 'unknown')
    }


async def test_device_rotation(device_id: str, method: str) -> dict:
    """Тестирование метода ротации устройства"""
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

        # Получаем текущий IP
        current_ip = None
        if device_type == "android" and device_manager:
            current_ip = await device_manager.get_device_external_ip(device_id)
        elif device_type == "usb_modem" and modem_manager:
            current_ip = await modem_manager.get_device_external_ip(device_id)

        # Выполняем тестовую ротацию
        import time
        start_time = time.time()

        logger.info(f"Testing rotation method '{method}' for device {device_id}")

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
            "device_type": device_type,
            "execution_time_seconds": round(execution_time, 2),
            "current_ip_before": current_ip,
            "new_ip_after": new_ip,
            "ip_changed": ip_changed,
            "result_message": result if success else f"Test rotation failed: {result}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recommendation": "success" if success and ip_changed else "try_different_method"
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
