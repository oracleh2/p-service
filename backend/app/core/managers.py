# backend/app/core/managers.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

from typing import Optional
from .device_manager import DeviceManager
from .proxy_server import ProxyServer
import structlog
import asyncio

logger = structlog.get_logger()

# Глобальные экземпляры менеджеров
_device_manager: Optional[DeviceManager] = None
_proxy_server: Optional[ProxyServer] = None
_rotation_manager = None
_stats_collector = None
_managers_initialized = False


async def init_managers():
    """Инициализация всех менеджеров"""
    global _device_manager, _proxy_server, _managers_initialized

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

        # Инициализация ProxyServer
        if _proxy_server is None:
            _proxy_server = ProxyServer(_device_manager, _stats_collector)
            # Не запускаем сразу, запустим позже в startup event
            logger.info("✅ Proxy server initialized")

        _managers_initialized = True
        logger.info("✅ All managers initialized successfully")

    except Exception as e:
        logger.error(f"❌ Error initializing managers: {e}")
        _managers_initialized = False
        raise


def get_device_manager() -> Optional[DeviceManager]:
    """Получение экземпляра DeviceManager"""
    global _device_manager

    # Если менеджер не инициализирован, создаем его синхронно
    if _device_manager is None:
        logger.info("Creating new DeviceManager instance")
        _device_manager = DeviceManager()

        # Пытаемся запустить асинхронно, если возможно
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Создаем задачу для запуска
                asyncio.create_task(_device_manager.start())
            else:
                # Если цикл не запущен, запускаем синхронно
                asyncio.run(_device_manager.start())
        except Exception as e:
            logger.warning(f"Could not start device manager immediately: {e}")

    return _device_manager


def get_proxy_server() -> Optional[ProxyServer]:
    """Получение экземпляра прокси-сервера"""
    return _proxy_server


def get_rotation_manager():
    """Получение экземпляра менеджера ротации"""
    return _rotation_manager


def set_rotation_manager(rotation_manager):
    """Установка экземпляра менеджера ротации"""
    global _rotation_manager
    _rotation_manager = rotation_manager


# Алиасы для совместимости со старым API
def get_modem_manager():
    """Алиас для get_device_manager() для совместимости"""
    return get_device_manager()


async def cleanup_managers():
    """Очистка всех менеджеров при завершении работы"""
    global _device_manager, _proxy_server

    try:
        if _proxy_server:
            await _proxy_server.stop()
            _proxy_server = None
            logger.info("✅ Proxy server stopped")

        if _device_manager:
            await _device_manager.stop()
            _device_manager = None
            logger.info("✅ Device manager stopped")

    except Exception as e:
        logger.error(f"❌ Error cleaning up managers: {e}")
