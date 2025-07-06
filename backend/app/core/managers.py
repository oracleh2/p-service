# Создайте новый файл: backend/app/core/managers.py

from typing import Optional
from .modem_manager import ModemManager

# Глобальные экземпляры менеджеров
_modem_manager: Optional[ModemManager] = None
_proxy_server = None
_rotation_manager = None


def init_managers():
    """Инициализация всех менеджеров"""
    global _modem_manager
    if _modem_manager is None:
        _modem_manager = ModemManager()


def get_modem_manager() -> Optional[ModemManager]:
    """Получение экземпляра ModemManager"""
    return _modem_manager


def get_proxy_server():
    """Получение экземпляра прокси-сервера"""
    return _proxy_server


def get_rotation_manager():
    """Получение экземпляра менеджера ротации"""
    return _rotation_manager


def set_proxy_server(proxy_server):
    """Установка экземпляра прокси-сервера"""
    global _proxy_server
    _proxy_server = proxy_server


def set_rotation_manager(rotation_manager):
    """Установка экземпляра менеджера ротации"""
    global _rotation_manager
    _rotation_manager = rotation_manager
