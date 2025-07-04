from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import timedelta
from typing import Optional

from ..models.database import get_db
from ..models.base import User
from ..utils.security import (
    verify_password,
    create_access_token,
    verify_token,
    get_password_hash,
    generate_api_key
)
from ..models.config import settings

router = APIRouter()
security = HTTPBearer()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    username: str
    role: str
    api_key: str


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    requests_limit: int
    requests_used: int
    api_key: str


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: AsyncSession = Depends(get_db)
):
    """Получение текущего пользователя из JWT токена"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_token(credentials.credentials, credentials_exception)

    stmt = select(User).where(User.username == token_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    """Получение активного пользователя"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_admin_user(current_user: User = Depends(get_current_active_user)):
    """Проверка прав администратора"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


@router.post("/login", response_model=LoginResponse)
async def login(
        login_data: LoginRequest,
        db: AsyncSession = Depends(get_db)
):
    """Аутентификация пользователя"""
    # Поиск пользователя
    stmt = select(User).where(User.username == login_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # Создание JWT токена
    access_token_expires = timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=str(user.id),
        username=user.username,
        role=user.role,
        api_key=user.api_key
    )


@router.post("/register", response_model=UserResponse)
async def register(
        user_data: UserCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_admin_user)  # Только админ может создавать пользователей
):
    """Регистрация нового пользователя"""
    # Проверка существования пользователя
    stmt = select(User).where(
        (User.username == user_data.username) | (User.email == user_data.email)
    )
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )

    # Создание пользователя
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        role=user_data.role,
        api_key=generate_api_key()
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UserResponse(
        id=str(new_user.id),
        username=new_user.username,
        email=new_user.email,
        role=new_user.role,
        is_active=new_user.is_active,
        requests_limit=new_user.requests_limit,
        requests_used=new_user.requests_used,
        api_key=new_user.api_key
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
        current_user: User = Depends(get_current_active_user)
):
    """Получение информации о текущем пользователе"""
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        requests_limit=current_user.requests_limit,
        requests_used=current_user.requests_used,
        api_key=current_user.api_key
    )


@router.post("/refresh-api-key")
async def refresh_api_key(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Обновление API ключа"""
    current_user.api_key = generate_api_key()
    await db.commit()

    return {"api_key": current_user.api_key, "message": "API key refreshed successfully"}


@router.post("/change-password")
async def change_password(
        old_password: str,
        new_password: str,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db)
):
    """Изменение пароля"""
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )

    current_user.password_hash = get_password_hash(new_password)
    await db.commit()

    return {"message": "Password changed successfully"}


@router.get("/users", response_model=list[UserResponse])
async def get_users(
        current_user: User = Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Получение списка пользователей (только для админа)"""
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            requests_limit=user.requests_limit,
            requests_used=user.requests_used,
            api_key=user.api_key
        )
        for user in users
    ]


@router.put("/users/{user_id}")
async def update_user(
        user_id: str,
        is_active: Optional[bool] = None,
        requests_limit: Optional[int] = None,
        role: Optional[str] = None,
        current_user: User = Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Обновление пользователя (только для админа)"""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if is_active is not None:
        user.is_active = is_active
    if requests_limit is not None:
        user.requests_limit = requests_limit
    if role is not None:
        user.role = role

    await db.commit()

    return {"message": "User updated successfully"}


@router.delete("/users/{user_id}")
async def delete_user(
        user_id: str,
        current_user: User = Depends(get_admin_user),
        db: AsyncSession = Depends(get_db)
):
    """Удаление пользователя (только для админа)"""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )

    await db.delete(user)
    await db.commit()

    return {"message": "User deleted successfully"}
