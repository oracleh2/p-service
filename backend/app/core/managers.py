# backend/app/core/managers.py - ОБНОВЛЕННАЯ ВЕРСИЯ С УЛУЧШЕННОЙ РОТАЦИЕЙ

from typing import Optional

from .dedicated_proxy_manager import DedicatedProxyManager
from .device_manager import DeviceManager
from .proxy_server import ProxyServer
from .enhanced_rotation_manager import EnhancedRotationManager
import structlog
import asyncio
from datetime import datetime, timezone, timedelta

logger = structlog.get_logger()

# Глобальные экземпляры менеджеров
_device_manager: Optional[DeviceManager] = None
_proxy_server: Optional[ProxyServer] = None
_enhanced_rotation_manager: Optional[EnhancedRotationManager] = None
_stats_collector = None
_managers_initialized = False
_dedicated_proxy_manager: Optional[DedicatedProxyManager] = None


async def init_managers():
    """Инициализация всех менеджеров"""
    global _device_manager, _proxy_server, _dedicated_proxy_manager, _enhanced_rotation_manager, _managers_initialized

    try:
        if _managers_initialized:
            logger.info("Managers already initialized, skipping...")
            return

        logger.info("Initializing managers...")

        # Инициализация DeviceManager
        if _device_manager is None:
            _device_manager = DeviceManager()
            await _device_manager.start()
            logger.info("✅ Device manager initialized")

        # Инициализация Enhanced Rotation Manager
        if _enhanced_rotation_manager is None:
            _enhanced_rotation_manager = EnhancedRotationManager()
            _enhanced_rotation_manager.device_manager = _device_manager  # Связываем с device manager
            await _enhanced_rotation_manager.start()
            logger.info("✅ Enhanced rotation manager initialized")

        # Инициализация ProxyServer
        if _proxy_server is None:
            _proxy_server = ProxyServer(_device_manager, _stats_collector)
            logger.info("✅ Proxy server initialized")

        # Инициализация DedicatedProxyManager
        if _dedicated_proxy_manager is None:
            _dedicated_proxy_manager = DedicatedProxyManager(_device_manager)
            await _dedicated_proxy_manager.start()
            logger.info("✅ Dedicated proxy manager initialized")

        _managers_initialized = True
        logger.info("✅ All managers initialized successfully")

    except Exception as e:
        logger.error(f"❌ Error initializing managers: {e}")
        _managers_initialized = False
        raise


def get_device_manager() -> Optional[DeviceManager]:
    """Получение экземпляра DeviceManager"""
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

        # Связываем с device manager если он существует
        if _device_manager:
            _enhanced_rotation_manager.device_manager = _device_manager

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


def get_modem_manager():
    """Алиас для get_device_manager() для совместимости"""
    return get_device_manager()


def set_rotation_manager(rotation_manager):
    """Установка экземпляра менеджера ротации (deprecated)"""
    global _enhanced_rotation_manager
    logger.warning("set_rotation_manager is deprecated, use get_enhanced_rotation_manager() instead")
    _enhanced_rotation_manager = rotation_manager


async def cleanup_managers():
    """Очистка всех менеджеров при завершении работы"""
    global _device_manager, _proxy_server, _dedicated_proxy_manager, _enhanced_rotation_manager

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

        if _dedicated_proxy_manager:
            await _dedicated_proxy_manager.stop()
            _dedicated_proxy_manager = None
            logger.info("✅ Dedicated proxy manager stopped")

    except Exception as e:
        logger.error(f"❌ Error cleaning up managers: {e}")


# Дополнительные утилиты для работы с ротацией
# async def perform_device_rotation(device_id: str, method: str = None) -> tuple[bool, str]:
#     """
#     Выполнение ротации устройства с использованием улучшенного менеджера
#
#     Args:
#         device_id: ID устройства
#         method: Принудительный метод ротации (опционально)
#
#     Returns:
#         tuple[bool, str]: (успех, сообщение/новый_IP)
#     """
#     rotation_manager = get_enhanced_rotation_manager()
#     if not rotation_manager:
#         return False, "Enhanced rotation manager not available"
#
#     try:
#         return await rotation_manager.rotate_device_ip(device_id)
#     except Exception as e:
#         logger.error(f"Error in device rotation: {e}")
#         return False, f"Rotation error: {str(e)}"
#
#
# async def get_device_rotation_methods(device_id: str) -> dict:
#     """Получение доступных методов ротации для устройства"""
#     device_manager = get_device_manager()
#     if not device_manager:
#         return {"error": "Device manager not available"}
#
#     try:
#         all_devices = await device_manager.get_all_devices()
#         device_info = all_devices.get(device_id)
#
#         if not device_info:
#             return {"error": "Device not found"}
#
#         device_type = device_info.get('type', 'unknown')
#
#         # Методы ротации для каждого типа устройства
#         rotation_methods = {
#             'android': [
#                 {
#                     'method': 'data_toggle',
#                     'name': 'Переключение мобильных данных',
#                     'description': 'Отключение и включение мобильных данных',
#                     'recommended': True,
#                     'risk_level': 'low'
#                 },
#                 {
#                     'method': 'airplane_mode',
#                     'name': 'Режим полета',
#                     'description': 'Включение и отключение режима полета',
#                     'recommended': False,
#                     'risk_level': 'medium'
#                 },
#                 {
#                     'method': 'usb_reconnect',
#                     'name': 'Переподключение USB',
#                     'description': 'Переподключение USB tethering',
#                     'recommended': False,
#                     'risk_level': 'medium'
#                 }
#             ],
#             'usb_modem': [
#                 {
#                     'method': 'at_commands',
#                     'name': 'AT команды',
#                     'description': 'Ротация через AT команды модема',
#                     'recommended': True,
#                     'risk_level': 'low'
#                 },
#                 {
#                     'method': 'interface_restart',
#                     'name': 'Перезапуск интерфейса',
#                     'description': 'Перезапуск сетевого интерфейса',
#                     'recommended': False,
#                     'risk_level': 'medium'
#                 }
#             ],
#             'raspberry_pi': [
#                 {
#                     'method': 'ppp_restart',
#                     'name': 'Перезапуск PPP',
#                     'description': 'Перезапуск PPP соединения',
#                     'recommended': True,
#                     'risk_level': 'low'
#                 }
#             ],
#             'network_device': [
#                 {
#                     'method': 'interface_restart',
#                     'name': 'Перезапуск интерфейса',
#                     'description': 'Перезапуск сетевого интерфейса',
#                     'recommended': True,
#                     'risk_level': 'low'
#                 }
#             ]
#         }
#
#         available_methods = rotation_methods.get(device_type, [])
#
#         return {
#             "device_id": device_id,
#             "device_type": device_type,
#             "available_methods": available_methods,
#             "current_method": device_info.get('rotation_method', 'data_toggle'),
#             "device_status": device_info.get('status', 'unknown')
#         }
#
#     except Exception as e:
#         logger.error(f"Error getting rotation methods: {e}")
#         return {"error": str(e)}
#
#
# async def test_device_rotation(device_id: str, method: str) -> dict:
#     """Тестирование метода ротации устройства"""
#     device_manager = get_device_manager()
#     rotation_manager = get_enhanced_rotation_manager()
#
#     if not device_manager or not rotation_manager:
#         return {"error": "Required managers not available"}
#
#     try:
#         # Получаем текущий IP
#         current_ip = await device_manager.get_device_external_ip(device_id)
#
#         # Выполняем тестовую ротацию
#         import time
#         start_time = time.time()
#         success, result = await rotation_manager.rotate_device_ip(device_id)
#         execution_time = time.time() - start_time
#
#         # Проверяем новый IP
#         new_ip = await device_manager.get_device_external_ip(device_id)
#         ip_changed = new_ip != current_ip if current_ip and new_ip else False
#
#         return {
#             "success": success,
#             "method": method,
#             "device_id": device_id,
#             "execution_time_seconds": round(execution_time, 2),
#             "current_ip_before": current_ip,
#             "new_ip_after": new_ip,
#             "ip_changed": ip_changed,
#             "result_message": result,
#             "timestamp": datetime.now(timezone.utc).isoformat(),
#             "recommendation": "success" if success and ip_changed else "try_different_method"
#         }
#
#     except Exception as e:
#         logger.error(f"Error testing rotation: {e}")
#         return {"error": str(e)}


async def perform_device_rotation(device_id: str, method: str = None) -> tuple[bool, str]:
    """
    Выполнение ротации устройства с использованием DeviceManager (не EnhancedRotationManager)

    Args:
        device_id: ID устройства (строковый ID из DeviceManager)
        method: Принудительный метод ротации (опционально)

    Returns:
        tuple[bool, str]: (успех, сообщение/новый_IP)
    """
    device_manager = get_device_manager()
    if not device_manager:
        return False, "Device manager not available"

    try:
        # ИСПРАВЛЕНО: Используем DeviceManager напрямую вместо EnhancedRotationManager
        # так как у нас строковые ID, а не UUID

        logger.info(f"Performing rotation for device: {device_id} with method: {method}")

        # Получаем информацию об устройстве
        all_devices = await device_manager.get_all_devices()
        device_info = all_devices.get(device_id)

        if not device_info:
            return False, f"Device {device_id} not found"

        # Получаем старый IP для сравнения
        old_ip = await device_manager.get_device_external_ip(device_id)

        # Выполняем ротацию через DeviceManager
        success = await device_manager.rotate_device_ip(device_id)

        if success:
            # Ждем стабилизации соединения
            await asyncio.sleep(15)

            # Получаем новый IP
            new_ip = await device_manager.get_device_external_ip(device_id)

            if new_ip and new_ip != old_ip:
                logger.info(f"IP rotation successful: {old_ip} -> {new_ip}")
                return True, new_ip
            elif new_ip:
                logger.warning(f"IP rotation executed but IP didn't change: {new_ip}")
                return True, new_ip  # Считаем успехом, даже если IP не изменился
            else:
                logger.warning("IP rotation executed but couldn't get new IP")
                return True, "Rotation completed"
        else:
            return False, "Device rotation failed"

    except Exception as e:
        logger.error(f"Error in device rotation: {e}")
        return False, f"Rotation error: {str(e)}"


async def get_device_rotation_methods(device_id: str) -> dict:
    """Получение доступных методов ротации для устройства"""
    device_manager = get_device_manager()
    if not device_manager:
        return {"error": "Device manager not available"}

    try:
        all_devices = await device_manager.get_all_devices()
        device_info = all_devices.get(device_id)

        if not device_info:
            return {"error": "Device not found"}

        device_type = device_info.get('type', 'unknown')

        # Методы ротации для каждого типа устройства
        rotation_methods = {
            'android': [
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
            ],
            'usb_modem': [
                {
                    'method': 'at_commands',
                    'name': 'AT команды',
                    'description': 'Ротация через AT команды модема (CFUN=0/1)',
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
                    'method': 'usb_reset',
                    'name': 'USB сброс',
                    'description': 'Физический сброс USB модема',
                    'recommended': False,
                    'risk_level': 'high'
                }
            ],
            'raspberry_pi': [
                {
                    'method': 'ppp_restart',
                    'name': 'Перезапуск PPP',
                    'description': 'Перезапуск PPP соединения',
                    'recommended': True,
                    'risk_level': 'low'
                },
                {
                    'method': 'modem_reset',
                    'name': 'Сброс модема',
                    'description': 'Сброс модема через GPIO или USB',
                    'recommended': False,
                    'risk_level': 'medium'
                }
            ],
            'network_device': [
                {
                    'method': 'interface_restart',
                    'name': 'Перезапуск интерфейса',
                    'description': 'Перезапуск сетевого интерфейса',
                    'recommended': True,
                    'risk_level': 'low'
                },
                {
                    'method': 'dhcp_renew',
                    'name': 'Обновление DHCP',
                    'description': 'Запрос нового IP через DHCP',
                    'recommended': False,
                    'risk_level': 'low'
                }
            ]
        }

        available_methods = rotation_methods.get(device_type, [])

        return {
            "device_id": device_id,
            "device_type": device_type,
            "available_methods": available_methods,
            "current_method": device_info.get('rotation_method', 'data_toggle'),
            "device_status": device_info.get('status', 'unknown')
        }

    except Exception as e:
        logger.error(f"Error getting rotation methods: {e}")
        return {"error": str(e)}


async def test_device_rotation(device_id: str, method: str) -> dict:
    """Тестирование метода ротации устройства"""
    device_manager = get_device_manager()

    if not device_manager:
        return {"error": "Device manager not available"}

    try:
        # Получаем информацию об устройстве
        all_devices = await device_manager.get_all_devices()
        device_info = all_devices.get(device_id)

        if not device_info:
            return {"error": "Device not found"}

        # Получаем текущий IP
        current_ip = await device_manager.get_device_external_ip(device_id)

        # Выполняем тестовую ротацию
        import time
        start_time = time.time()

        logger.info(f"Testing rotation method '{method}' for device {device_id}")

        # Используем обычную ротацию DeviceManager для тестирования
        success = await device_manager.rotate_device_ip(device_id)
        execution_time = time.time() - start_time

        # Ждем стабилизации
        await asyncio.sleep(10)

        # Проверяем новый IP
        new_ip = await device_manager.get_device_external_ip(device_id)
        ip_changed = new_ip != current_ip if current_ip and new_ip else False

        return {
            "success": success,
            "method": method,
            "device_id": device_id,
            "execution_time_seconds": round(execution_time, 2),
            "current_ip_before": current_ip,
            "new_ip_after": new_ip,
            "ip_changed": ip_changed,
            "result_message": "Test rotation completed successfully" if success else "Test rotation failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recommendation": "success" if success and ip_changed else "try_different_method"
        }

    except Exception as e:
        logger.error(f"Error testing rotation: {e}")
        return {"error": str(e)}
