from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class ProxyDevice(Base):
    __tablename__ = "proxy_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    device_type = Column(String(50), nullable=False)  # 'android', 'usb_modem', 'raspberry_pi'
    ip_address = Column(String(45), nullable=False)
    port = Column(Integer, nullable=False)
    status = Column(String(50), default='offline')  # 'online', 'offline', 'busy', 'maintenance'
    current_external_ip = Column(String(45))
    operator = Column(String(100))  # 'МТС', 'Билайн', 'Мегафон', 'Теле2'
    region = Column(String(100))
    last_heartbeat = Column(DateTime, default=func.now())
    last_ip_rotation = Column(DateTime)
    rotation_interval = Column(Integer, default=600)  # секунды
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    avg_response_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Новые поля для индивидуальных прокси
    dedicated_port = Column(Integer, unique=True, nullable=True)
    proxy_username = Column(String(255), nullable=True)
    proxy_password = Column(String(255), nullable=True)
    proxy_enabled = Column(Boolean, default=True, nullable=True)


class RotationConfig(Base):
    __tablename__ = "rotation_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), nullable=False)
    rotation_method = Column(String(50), nullable=False)  # 'airplane_mode', 'data_toggle', 'api_call'
    rotation_interval = Column(Integer, nullable=False)
    auto_rotation = Column(Boolean, default=True)
    rotation_url = Column(String(500))  # для API ротации
    auth_token = Column(String(255))
    rotation_success_rate = Column(Float, default=0.0)
    last_successful_rotation = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True))
    client_ip = Column(String(45))
    target_url = Column(String(1000))
    method = Column(String(10))
    status_code = Column(Integer)
    response_time_ms = Column(Integer)
    external_ip = Column(String(45))
    user_agent = Column(Text)
    request_size = Column(Integer)
    response_size = Column(Integer)
    error_message = Column(Text)
    created_at = Column(DateTime, default=func.now())


class IpHistory(Base):
    __tablename__ = "ip_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), nullable=False)
    ip_address = Column(String(45), nullable=False)
    first_seen = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, default=func.now())
    total_requests = Column(Integer, default=0)
    operator = Column(String(100))
    geo_location = Column(String(100))
    city = Column(String(100))
    is_blocked = Column(Boolean, default=False)
    blocked_reason = Column(Text)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(255), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    api_key = Column(String(255), unique=True)
    role = Column(String(50), default='user')  # 'admin', 'user'
    is_active = Column(Boolean, default=True)
    requests_limit = Column(Integer, default=10000)
    requests_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class UsageStats(Base):
    __tablename__ = "usage_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True))
    user_id = Column(UUID(as_uuid=True))
    date = Column(DateTime, nullable=False)
    requests_count = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    avg_response_time_ms = Column(Integer, default=0)
    unique_ips_count = Column(Integer, default=0)
    data_transferred_mb = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())


class SystemConfig(Base):
    __tablename__ = "system_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(255), nullable=False, unique=True)
    value = Column(Text, nullable=False)
    description = Column(Text)
    config_type = Column(String(50), default='string')  # 'string', 'integer', 'boolean', 'json'
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
