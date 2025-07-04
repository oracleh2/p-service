from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from ..database import get_db
from ..models.base import ProxyDevice, RotationConfig, RequestLog, IpHistory
from ..api.auth import get_current_active_user, get_admin_user
from ..main import get_modem_manager, get_rotation_manager
from ..utils.security import validate_ip_address, validate_port

router = APIRouter()


class DeviceCreate(BaseModel):
    name: str
    device_type: str
    ip_address: str
    port: int
    operator: Optional[str] = None
    region: Optional[str] = None
    rotation_interval: int = 600

    @validator('device_type')
    def validate_device_type(cls, v):
        allowed_types = ['android', 'usb_modem', 'raspberry_pi']
        if v not in allowed_types:
            raise ValueError(f'Device type must be one of: {allowed_types}')
        return v

    @validator('ip_address')
    def validate_ip(cls, v):
        if not validate_ip_address(v):
            raise ValueError('Invalid IP address')
        return v

    @validator('port')
    def validate_port_number(cls, v):
        if not validate_port(v):
            raise ValueError('Port must be between 1 and 65535')
        return v


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    operator: Optional[str] = None
    region: Optional[str] = None
    rotation_interval: Optional[int] = None
    status: Optional[str] = None

    @validator('ip_address')
    def validate_ip(cls, v):
        if v is not None and not validate_ip_address(v):
            raise ValueError('Invalid IP address')
        return v

    @validator('port')
    def validate_port_number(cls, v):
        if v is not None and not validate_port(v):
            raise ValueError('Port must be between 1 and 65535')
        return v

    @validator('status')
    def validate_status(cls, v):
        if v is not None:
            allowed_statuses = ['online', 'offline', 'busy', 'maintenance']
            if v not in allowed_statuses:
                raise ValueError(f'Status must be one of: {allowed_statuses}')
        return v


class RotationConfigCreate(BaseModel):
    device_id: str
    rotation_method: str
    rotation_interval: int
    auto_rotation: bool = True
    rotation_url: Optional[str] = None
    auth_token: Optional[str] = None

    @validator('rotation_method')
    def validate_rotation_method(cls, v):
        allowed_methods = ['airplane_mode', 'data_toggle', 'api_call', 'network_reset']
        if v not in allowed_methods:
            raise ValueError(f'Rotation method must be one of: {allowed_methods}')
        return v


class DeviceResponse(BaseModel):
    id: str
    name: str
    device_type: str
    ip_address: str
    port: int
    status: str
    current_external_ip: Optional[str]
    operator: Optional[str]
    region: Optional[str]
    last_heartbeat: Optional[datetime]
    last_ip_rotation: Optional[datetime]
    rotation_interval: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: int
    created_at: datetime
    updated_at: datetime


class DeviceStatsResponse(BaseModel):
    device_id: str
    device_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time_ms: int
    unique_ips: int
    last_24h_requests: int
    uptime_percentage: float


@router.get("/", response_model=List[DeviceResponse])
async def get_devices(
        status: Optional[str] = None,
        device_type: Optional[str] = None,
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение списка устройств"""
    query = select(ProxyDevice)

    if status:
        query = query.where(ProxyDevice.status == status)
    if device_type:
        query = query.where(ProxyDevice.device_type == device_type)

    query = query.order_by(ProxyDevice.created_at.desc())

    result = await db.execute(query)
    devices = result.scalars().all()

    return [
        DeviceResponse(
            id=str(device.id),
            name=device.name,
            device_type=device.device_type,
            ip_address=device.ip_address,
            port=device.port,
            status=device.status,
            current_external_ip=device.current_external_ip,
            operator=device.operator,
            region=device.region,
            last_heartbeat=device.last_heartbeat,
            last_ip_rotation=device.last_ip_rotation,
            rotation_interval=device.rotation_interval,
            total_requests=device.total_requests,
            successful_requests=device.successful_requests,
            failed_requests=device.failed_requests,
            avg_response_time_ms=device.avg_response_time_ms,
            created_at=device.created_at,
            updated_at=device.updated_at
        )
        for device in devices
    ]


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
        device_id: str,
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение информации об устройстве"""
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format"
        )

    stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    return DeviceResponse(
        id=str(device.id),
        name=device.name,
        device_type=device.device_type,
        ip_address=device.ip_address,
        port=device.port,
        status=device.status,
        current_external_ip=device.current_external_ip,
        operator=device.operator,
        region=device.region,
        last_heartbeat=device.last_heartbeat,
        last_ip_rotation=device.last_ip_rotation,
        rotation_interval=device.rotation_interval,
        total_requests=device.total_requests,
        successful_requests=device.successful_requests,
        failed_requests=device.failed_requests,
        avg_response_time_ms=device.avg_response_time_ms,
        created_at=device.created_at,
        updated_at=device.updated_at
    )


@router.post("/", response_model=DeviceResponse)
async def create_device(
        device_data: DeviceCreate,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Создание нового устройства"""
    # Проверка уникальности имени
    stmt = select(ProxyDevice).where(ProxyDevice.name == device_data.name)
    result = await db.execute(stmt)
    existing_device = result.scalar_one_or_none()

    if existing_device:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device with this name already exists"
        )

    # Создание устройства
    new_device = ProxyDevice(
        name=device_data.name,
        device_type=device_data.device_type,
        ip_address=device_data.ip_address,
        port=device_data.port,
        operator=device_data.operator,
        region=device_data.region,
        rotation_interval=device_data.rotation_interval,
        status='offline'
    )

    db.add(new_device)
    await db.commit()
    await db.refresh(new_device)

    # Создание конфигурации ротации по умолчанию
    rotation_config = RotationConfig(
        device_id=new_device.id,
        rotation_method='airplane_mode',
        rotation_interval=device_data.rotation_interval,
        auto_rotation=True
    )

    db.add(rotation_config)
    await db.commit()

    return DeviceResponse(
        id=str(new_device.id),
        name=new_device.name,
        device_type=new_device.device_type,
        ip_address=new_device.ip_address,
        port=new_device.port,
        status=new_device.status,
        current_external_ip=new_device.current_external_ip,
        operator=new_device.operator,
        region=new_device.region,
        last_heartbeat=new_device.last_heartbeat,
        last_ip_rotation=new_device.last_ip_rotation,
        rotation_interval=new_device.rotation_interval,
        total_requests=new_device.total_requests,
        successful_requests=new_device.successful_requests,
        failed_requests=new_device.failed_requests,
        avg_response_time_ms=new_device.avg_response_time_ms,
        created_at=new_device.created_at,
        updated_at=new_device.updated_at
    )


@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
        device_id: str,
        device_data: DeviceUpdate,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Обновление устройства"""
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format"
        )

    stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    # Обновление полей
    update_data = device_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)

    await db.commit()
    await db.refresh(device)

    return DeviceResponse(
        id=str(device.id),
        name=device.name,
        device_type=device.device_type,
        ip_address=device.ip_address,
        port=device.port,
        status=device.status,
        current_external_ip=device.current_external_ip,
        operator=device.operator,
        region=device.region,
        last_heartbeat=device.last_heartbeat,
        last_ip_rotation=device.last_ip_rotation,
        rotation_interval=device.rotation_interval,
        total_requests=device.total_requests,
        successful_requests=device.successful_requests,
        failed_requests=device.failed_requests,
        avg_response_time_ms=device.avg_response_time_ms,
        created_at=device.created_at,
        updated_at=device.updated_at
    )


@router.delete("/{device_id}")
async def delete_device(
        device_id: str,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Удаление устройства"""
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format"
        )

    stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    await db.delete(device)
    await db.commit()

    return {"message": "Device deleted successfully"}


@router.post("/{device_id}/rotate")
async def rotate_device_ip(
        device_id: str,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Принудительная ротация IP устройства"""
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format"
        )

    rotation_manager = get_rotation_manager()
    if not rotation_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rotation manager not available"
        )

    success = await rotation_manager.rotate_device_ip(device_uuid)

    if success:
        return {"message": "IP rotation initiated successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to initiate IP rotation"
        )


@router.get("/{device_id}/stats", response_model=DeviceStatsResponse)
async def get_device_stats(
        device_id: str,
        current_user=Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение статистики устройства"""
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format"
        )

    # Получение информации об устройстве
    stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    # Получение статистики за последние 24 часа
    from datetime import datetime, timedelta
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    stmt_24h = select(func.count(RequestLog.id)).where(
        RequestLog.device_id == device_uuid,
        RequestLog.created_at >= yesterday
    )
    result_24h = await db.execute(stmt_24h)
    last_24h_requests = result_24h.scalar() or 0

    # Получение количества уникальных IP
    stmt_ips = select(func.count(IpHistory.id.distinct())).where(
        IpHistory.device_id == device_uuid
    )
    result_ips = await db.execute(stmt_ips)
    unique_ips = result_ips.scalar() or 0

    # Расчет процента успешности
    success_rate = 0.0
    if device.total_requests > 0:
        success_rate = (device.successful_requests / device.total_requests) * 100

    # Расчет uptime (упрощенный)
    uptime_percentage = 95.0  # Заглушка, в реальности нужно считать на основе heartbeat

    return DeviceStatsResponse(
        device_id=str(device.id),
        device_name=device.name,
        total_requests=device.total_requests,
        successful_requests=device.successful_requests,
        failed_requests=device.failed_requests,
        success_rate=success_rate,
        avg_response_time_ms=device.avg_response_time_ms,
        unique_ips=unique_ips,
        last_24h_requests=last_24h_requests,
        uptime_percentage=uptime_percentage
    )


@router.post("/{device_id}/heartbeat")
async def device_heartbeat(
        device_id: str,
        external_ip: Optional[str] = None,
        db: AsyncSession = Depends(get_db)
):
    """Heartbeat от устройства"""
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format"
        )

    # Обновление времени последнего heartbeat
    stmt = update(ProxyDevice).where(ProxyDevice.id == device_uuid).values(
        last_heartbeat=datetime.now(timezone.utc),
        status='online',
        current_external_ip=external_ip
    )

    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    await db.commit()

    return {"message": "Heartbeat received successfully"}


@router.post("/{device_id}/restart")
async def restart_device(
        device_id: str,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Перезапуск устройства"""
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format"
        )

    device_manager = get_device_manager()
    if not device_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device manager not available"
        )

    success = await device_manager.restart_device(device_uuid)

    if success:
        return {"message": "Device restart initiated successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to initiate device restart"
        )


@router.put("/{device_id}/rotation-config")
async def update_rotation_config(
        device_id: str,
        config_data: RotationConfigCreate,
        current_user=Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Обновление конфигурации ротации устройства"""
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format"
        )

    # Проверка существования устройства
    stmt = select(ProxyDevice).where(ProxyDevice.id == device_uuid)
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    # Обновление или создание конфигурации ротации
    stmt = select(RotationConfig).where(RotationConfig.device_id == device_uuid)
    result = await db.execute(stmt)
    rotation_config = result.scalar_one_or_none()

    if rotation_config:
        # Обновление существующей конфигурации
        rotation_config.rotation_method = config_data.rotation_method
        rotation_config.rotation_interval = config_data.rotation_interval
        rotation_config.auto_rotation = config_data.auto_rotation
        rotation_config.rotation_url = config_data.rotation_url
        rotation_config.auth_token = config_data.auth_token
    else:
        # Создание новой конфигурации
        rotation_config = RotationConfig(
            device_id=device_uuid,
            rotation_method=config_data.rotation_method,
            rotation_interval=config_data.rotation_interval,
            auto_rotation=config_data.auto_rotation,
            rotation_url=config_data.rotation_url,
            auth_token=config_data.auth_token
        )
        db.add(rotation_config)

    await db.commit()

    return {"message": "Rotation configuration updated successfully"}