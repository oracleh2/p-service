# backend/app/core/managers.py - ОБНОВЛЕННЫЙ ДЛЯ УНИВЕРСАЛЬНОЙ СИСТЕМЫ

from typing import Optional
from .device_manager import DeviceManager
from .proxy_server import ProxyServer

# Глобальные экземпляры менеджеров
_device_manager: Optional[DeviceManager] = None
_proxy_server: Optional[ProxyServer] = None
_rotation_manager = None
_stats_collector = None


def init_managers():
    """Инициализация всех менеджеров"""
    global _device_manager, _proxy_server

    if _device_manager is None:
        _device_manager = DeviceManager()

    if _proxy_server is None:
        # Передаем device_manager в proxy_server
        _proxy_server = ProxyServer(_device_manager, _stats_collector)


def get_device_manager() -> Optional[DeviceManager]:
    """Получение экземпляра DeviceManager"""
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
