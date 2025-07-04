# backend/init_db.py
"""
Скрипт для инициализации базы данных
Создает таблицы и добавляет начальные данные
"""

import asyncio
import sys
import os
from pathlib import Path

# Добавляем путь к app для импорта модулей
sys.path.append(str(Path(__file__).parent))

from app.models.database import init_db, check_db_connection
from app.models.base import Base
from app.models.config import settings  # исправленный импорт
import structlog

logger = structlog.get_logger()


async def create_admin_user():
    """Создание администратора по умолчанию"""
    from app.models.database import AsyncSessionLocal
    from app.models.base import User
    from app.utils.security import get_password_hash, generate_api_key
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        try:
            # Проверяем, существует ли админ
            stmt = select(User).where(User.username == "admin")
            result = await session.execute(stmt)
            existing_admin = result.scalar_one_or_none()

            if existing_admin:
                print("✅ Администратор уже существует")
                print(f"   Логин: admin")
                print(f"   Email: {existing_admin.email}")
                print(f"   API Key: {existing_admin.api_key}")
                return existing_admin

            # Создаем администратора
            admin_user = User(
                username="admin",
                email="admin@localhost",
                password_hash=get_password_hash("admin123"),
                api_key=generate_api_key(),
                role="admin",
                is_active=True,
                requests_limit=100000
            )

            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)

            print("✅ Администратор создан успешно:")
            print(f"   Логин: admin")
            print(f"   Пароль: admin123")
            print(f"   Email: admin@localhost")
            print(f"   API Key: {admin_user.api_key}")

            return admin_user

        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка создания администратора: {e}")
            raise


async def create_system_config():
    """Создание системной конфигурации по умолчанию"""
    from app.models.database import AsyncSessionLocal
    from app.models.base import SystemConfig
    from sqlalchemy import select

    default_configs = {
        "rotation_interval": {
            "value": "600",
            "description": "Интервал автоматической ротации IP в секундах",
            "config_type": "integer"
        },
        "auto_rotation_enabled": {
            "value": "true",
            "description": "Включить автоматическую ротацию IP",
            "config_type": "boolean"
        },
        "max_devices": {
            "value": "50",
            "description": "Максимальное количество устройств",
            "config_type": "integer"
        },
        "max_requests_per_minute": {
            "value": "100",
            "description": "Максимальное количество запросов в минуту на устройство",
            "config_type": "integer"
        },
        "request_timeout": {
            "value": "30",
            "description": "Таймаут запросов в секундах",
            "config_type": "integer"
        },
        "health_check_interval": {
            "value": "30",
            "description": "Интервал проверки здоровья устройств в секундах",
            "config_type": "integer"
        }
    }

    async with AsyncSessionLocal() as session:
        try:
            created_count = 0

            for key, config in default_configs.items():
                # Проверяем, существует ли конфигурация
                stmt = select(SystemConfig).where(SystemConfig.key == key)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    system_config = SystemConfig(
                        key=key,
                        value=config["value"],
                        description=config["description"],
                        config_type=config["config_type"]
                    )
                    session.add(system_config)
                    created_count += 1

            if created_count > 0:
                await session.commit()
                print(f"✅ Создано {created_count} записей системной конфигурации")
            else:
                print("✅ Системная конфигурация уже существует")

        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка создания системной конфигурации: {e}")
            raise


async def show_connection_info():
    """Показать информацию о подключении"""
    print("\n🔗 Информация о подключении:")
    print(f"   База данных: {settings.DATABASE_URL}")
    print(f"   Redis: {settings.REDIS_URL}")
    print(f"   API сервер: http://localhost:{settings.API_PORT}")
    print(f"   Прокси сервер: http://localhost:{settings.PROXY_PORT}")


async def main():
    """Основная функция инициализации"""
    print("🔧 Инициализация базы данных Mobile Proxy Service")
    print("=" * 60)

    try:
        # Проверяем подключение к БД
        print("🔍 Проверка подключения к базе данных...")
        if not await check_db_connection():
            print("❌ Не удается подключиться к базе данных")
            print("   Убедитесь, что PostgreSQL запущен и доступен")
            return False
        print("✅ Подключение к базе данных успешно")

        # Создаем таблицы
        print("\n📋 Создание таблиц...")
        await init_db()
        print("✅ Таблицы созданы успешно")

        # Создаем администратора
        print("\n👤 Создание администратора...")
        await create_admin_user()

        # Создаем системную конфигурацию
        print("\n⚙️  Создание системной конфигурации...")
        await create_system_config()

        # Показываем информацию о подключении
        await show_connection_info()

        print("\n🎉 Инициализация завершена успешно!")
        print("\n📋 Следующие шаги:")
        print("   1. Запустите backend сервер: python -m uvicorn app.main:app --reload")
        print("   2. Откройте http://localhost:8000/docs для проверки API")
        print("   3. Войдите в систему: admin / admin123")

        return True

    except Exception as e:
        print(f"\n❌ Ошибка инициализации: {e}")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Инициализация прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        sys.exit(1)
