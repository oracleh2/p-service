from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from pydantic import BaseModel
import secrets
import string
from ..config import settings

# Настройка контекста для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Хеширование пароля"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Создание JWT токена"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def verify_token(token: str, credentials_exception):
    """Проверка JWT токена"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    return token_data


def generate_api_key(length: int = None) -> str:
    """Генерация API ключа"""
    if length is None:
        length = 32  # используем константу вместо settings.API_KEY_LENGTH

    alphabet = string.ascii_letters + string.digits
    api_key = ''.join(secrets.choice(alphabet) for _ in range(length))
    return api_key


def validate_api_key(api_key: str) -> bool:
    """Валидация API ключа"""
    if not api_key:
        return False

    # Проверяем длину
    if len(api_key) != 32:  # используем константу
        return False

    # Проверяем символы
    allowed_chars = set(string.ascii_letters + string.digits)
    if not all(char in allowed_chars for char in api_key):
        return False

    return True


class RateLimiter:
    """Простой rate limiter для API"""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_rate_limit(self, key: str, limit: int, window: int = 60) -> bool:
        """
        Проверка лимита запросов
        key: уникальный ключ (IP, user_id и т.д.)
        limit: количество запросов
        window: окно времени в секундах
        """
        try:
            current_time = datetime.now().timestamp()
            pipe = self.redis.pipeline()

            # Получаем текущий счетчик
            pipe.get(key)
            # Устанавливаем TTL если ключ новый
            pipe.expire(key, window)

            results = await pipe.execute()
            current_count = int(results[0] or 0)

            if current_count >= limit:
                return False

            # Увеличиваем счетчик
            await self.redis.incr(key)
            return True

        except Exception:
            # В случае ошибки Redis разрешаем запрос
            return True

    async def get_remaining_requests(self, key: str, limit: int) -> int:
        """Получение количества оставшихся запросов"""
        try:
            current_count = await self.redis.get(key)
            current_count = int(current_count or 0)
            return max(0, limit - current_count)
        except Exception:
            return limit


def generate_device_token(device_id: str, device_name: str) -> str:
    """Генерация токена для устройства"""
    data = {
        "device_id": device_id,
        "device_name": device_name,
        "type": "device"
    }
    return create_access_token(data, expires_delta=timedelta(days=30))


def verify_device_token(token: str) -> Optional[dict]:
    """Проверка токена устройства"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "device":
            return None
        return {
            "device_id": payload.get("device_id"),
            "device_name": payload.get("device_name")
        }
    except JWTError:
        return None


class SecurityHeaders:
    """Класс для добавления security headers"""

    @staticmethod
    def get_security_headers() -> dict:
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }


def mask_sensitive_data(data: str, mask_char: str = "*", keep_start: int = 2, keep_end: int = 2) -> str:
    """Маскирование чувствительных данных"""
    if len(data) <= keep_start + keep_end:
        return mask_char * len(data)

    return data[:keep_start] + mask_char * (len(data) - keep_start - keep_end) + data[-keep_end:]


def validate_ip_address(ip: str) -> bool:
    """Валидация IP адреса"""
    import ipaddress
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def validate_port(port: int) -> bool:
    """Валидация порта"""
    return 1 <= port <= 65535


def is_safe_url(url: str) -> bool:
    """Проверка безопасности URL"""
    import re

    # Простая проверка на основные протоколы
    if not re.match(r'^https?://', url):
        return False

    # Проверка на локальные адреса
    local_patterns = [
        r'localhost',
        r'127\.0\.0\.1',
        r'192\.168\.',
        r'10\.',
        r'172\.1[6-9]\.',
        r'172\.2[0-9]\.',
        r'172\.3[0-1]\.',
        r'0\.0\.0\.0'
    ]

    for pattern in local_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return False

    return True
