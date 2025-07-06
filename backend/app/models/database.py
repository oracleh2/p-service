from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from redis.asyncio import Redis
import redis
from typing import AsyncGenerator
from ..config import settings
from .base import Base
import structlog

logger = structlog.get_logger()

# Асинхронный движок базы данных
async_engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=3600,  # 1 час
)

# Синхронный движок для миграций
sync_engine = create_engine(
    settings.database_url.replace("postgresql://", "postgresql://"),
    pool_size=10,
    max_overflow=20,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Создаем session maker
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

# Синхронная сессия для миграций
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


# Dependency для получения сессии БД
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error("Database session error", error=str(e))
            raise
        finally:
            await session.close()


# Redis подключение
redis_client = None


async def get_redis() -> Redis:
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(
            settings.redis_url,
            encoding="utf8",
            decode_responses=True,
            max_connections=settings.redis_pool_size
        )
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


# Инициализация базы данных
async def init_db():
    """Создание таблиц и начальных данных"""
    try:
        # Создаем таблицы
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Добавляем начальные данные
        await create_initial_data()

        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise


async def create_initial_data():
    """Создание начальных данных системы"""
    from .base import SystemConfig, User
    from ..utils.security import get_password_hash, generate_api_key
    from .config import DEFAULT_SYSTEM_CONFIG

    async with AsyncSessionLocal() as session:
        try:
            # Создаем системную конфигурацию по умолчанию
            for key, config in DEFAULT_SYSTEM_CONFIG.items():
                # Проверяем, существует ли уже такая конфигурация
                from sqlalchemy import select
                stmt = select(SystemConfig).where(SystemConfig.key == key)
                existing = await session.execute(stmt)
                if not existing.scalar_one_or_none():
                    system_config = SystemConfig(
                        key=key,
                        value=config["value"],
                        description=config["description"],
                        config_type=config["config_type"]
                    )
                    session.add(system_config)

            # Создаем администратора по умолчанию
            stmt = select(User).where(User.username == "admin")
            existing_admin = await session.execute(stmt)
            if not existing_admin.scalar_one_or_none():
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
            logger.info("Initial data created successfully")

        except Exception as e:
            await session.rollback()
            logger.error("Failed to create initial data", error=str(e))
            raise


# Проверка подключения к БД
async def check_db_connection():
    """Проверка подключения к базе данных"""
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False


# Проверка подключения к Redis
async def check_redis_connection():
    """Проверка подключения к Redis"""
    try:
        redis_conn = await get_redis()
        await redis_conn.ping()
        return True
    except Exception as e:
        logger.error("Redis connection failed", error=str(e))
        return False


# Получение конфигурации из БД
async def get_system_config(key: str, default_value: str = None):
    """Получение значения конфигурации из БД"""
    from sqlalchemy import select
    from .base import SystemConfig

    async with AsyncSessionLocal() as session:
        try:
            stmt = select(SystemConfig).where(SystemConfig.key == key)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                if config.config_type == "integer":
                    return int(config.value)
                elif config.config_type == "boolean":
                    return config.value.lower() in ("true", "1", "yes", "on")
                elif config.config_type == "json":
                    import json
                    return json.loads(config.value)
                else:
                    return config.value
            else:
                return default_value
        except Exception as e:
            logger.error("Failed to get system config", key=key, error=str(e))
            return default_value


# Обновление конфигурации в БД
async def update_system_config(key: str, value: str):
    """Обновление значения конфигурации в БД"""
    from sqlalchemy import select
    from .base import SystemConfig

    async with AsyncSessionLocal() as session:
        try:
            stmt = select(SystemConfig).where(SystemConfig.key == key)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                config.value = str(value)
                await session.commit()
                logger.info("System config updated", key=key, value=value)
                return True
            else:
                logger.warning("System config not found", key=key)
                return False
        except Exception as e:
            await session.rollback()
            logger.error("Failed to update system config", key=key, error=str(e))
            return False
