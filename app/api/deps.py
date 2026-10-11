"""Зависимости API: аутентификация (JWT веб-панели, API Key бота), текущий пользователь, права."""
import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.users import User
from app.repositories.users_repo import UserRepository
from app.services.ticket_service import TicketActor

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _load_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User:
    repo = UserRepository(session)
    user = await repo.get_with_roles(user_id)
    if user is None or user.is_deleted:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")
    return user


async def get_current_user(
    request: Request,
    creds=Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Аутентификация веб-панели: JWT Bearer токен из /auth/login."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется Bearer токен")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Токен истёк")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Некорректный токен")
    user = await _load_user_by_id(session, uuid.UUID(payload["sub"]))
    request.state.current_user = user
    return user


async def get_service_or_user(
    request: Request,
    api_key: str | None = Depends(api_key_header),
    creds=Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Служебная аутентификация для бота: X-API-Key + параметр ?user_id=... либо обычный JWT.

    Бот MAX работает от имени конечного пользователя: передаёт его user_id
    (или max_user_id) вместе с сервисным ключом.
    """
    if api_key and api_key == settings.service_api_key:
        user_id = request.query_params.get("user_id")
        max_user_id = request.query_params.get("max_user_id")
        repo = UserRepository(session)
        user = None
        if user_id:
            user = await repo.get_with_roles(uuid.UUID(user_id))
        elif max_user_id:
            user = await repo.get_by_max_id(int(max_user_id))
        if user is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Пользователь от имени которого идёт запрос не найден"
            )
        request.state.current_user = user
        request.state.via_service_key = True
        return user
    return await get_current_user(request, creds, session)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    roles = UserRepository.role_codes_of(user)
    from app.core.security import is_admin

    if not is_admin(roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Требуются права администратора")
    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    roles = UserRepository.role_codes_of(user)
    from app.core.security import is_staff

    if not is_staff(roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Требуются права сотрудника (support/admin)")
    return user


def make_actor(user: User, request: Request) -> TicketActor:
    """Собрать контекст действия из пользователя и запроса."""
    roles = UserRepository.role_codes_of(user)
    ip = request.client.host if request.client else None
    return TicketActor(user_id=user.id, roles=roles, ip=ip)
