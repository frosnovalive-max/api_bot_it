"""Эндпоинты пользователей, аутентификации веб-панели (JWT) и модерации (жалобы)."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, make_actor, require_admin
from app.api.v1.common import ERROR_403, ERROR_404, build_page
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, is_md5_hash, verify_password
from app.models.moderation import Complaint
from app.repositories.misc_repos import ModerationRepository, WebAccountRepository
from app.repositories.users_repo import UserRepository
from app.schemas.common import Page
from app.schemas.users import (
    BlockRequest,
    ComplaintCreate,
    ComplaintOut,
    LoginRequest,
    TokenResponse,
    UserOut,
    UserUpdate,
)

router = APIRouter(tags=["Users & Moderation"])


def _user_out(user) -> UserOut:
    data = UserOut.model_validate(user)
    data.roles = sorted(UserRepository.role_codes_of(user))
    return data


# ---------------------------------------------------------------- Auth (JWT)
@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Вход в веб-панель (JWT)",
    description=(
        "Аутентификация через `web_accounts`. Логин/пароль проверяются по хэшу. "
        "**Важно:** если сохранён легаси MD5-хэш — при первом успешном входе он "
        "автоматически перезаписывается bcrypt-хэшем. Действие фиксируется в `audit_log`."
    ),
    responses={403: ERROR_403},
)
async def login(
    request: Request,
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    repo = WebAccountRepository(session)
    account = await repo.get_by_login(payload.login)
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")

    # Пересохранение MD5 → bcrypt при первом входе
    if is_md5_hash(account.password_hash):
        account.password_hash = hash_password(payload.password)

    from datetime import datetime, timezone

    account.last_login_at = datetime.now(timezone.utc)

    users_repo = UserRepository(session)
    user = await users_repo.get_with_roles(account.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь аккаунта не найден")
    if user.is_blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Учётная запись заблокирована")

    await ModerationRepository(session).write_audit(
        user_id=user.id,
        action="login",
        entity_type="web_account",
        entity_id=account.id,
        ip_address=request.client.host if request.client else None,
    )

    token = create_access_token(subject={"sub": str(user.id), "login": account.login})
    return TokenResponse(access_token=token, user=_user_out(user))


# ------------------------------------------------------------------- Users
@router.get(
    "/users",
    response_model=Page[UserOut],
    summary="Список пользователей",
    description=(
        "Пагинированный список с фильтрами: текстовый поиск (имя/фамилия/username), "
        "роль, блокировка, адрес. Требуются права сотрудника (support/admin)."
    ),
    responses={403: ERROR_403},
)
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    query: str | None = Query(None, description="Поиск по имени/фамилии/username"),
    role_code: str | None = Query(None, examples=["student"]),
    is_blocked: bool | None = None,
    address_id: uuid.UUID | None = None,
):
    items, total = await UserRepository(session).search(
        offset=(page - 1) * page_size,
        limit=page_size,
        query=query,
        role_code=role_code,
        is_blocked=is_blocked,
        address_id=address_id,
    )
    return {
        "items": [_user_out(u) for u in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get(
    "/users/me",
    response_model=UserOut,
    summary="Текущий пользователь",
    description="Профиль аутентифицированного пользователя (из JWT или сервисного ключа).",
)
async def me(current: Annotated[object, Depends(get_current_user)]):
    return _user_out(current)


@router.get(
    "/users/by-max-id/{max_user_id}",
    response_model=UserOut,
    summary="Поиск пользователя по MAX ID",
    description=(
        "Критично для будущего бота MAX: позволяет найти внутреннего пользователя "
        "по внешнему `user_id` из MAX API. Работает и по сервисному API-ключу бота."
    ),
    responses={404: ERROR_404},
)
async def get_by_max_id(
    max_user_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_current_user)],
):
    user = await UserRepository(session).get_by_max_id(max_user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Пользователь с max_user_id={max_user_id} не найден")
    return _user_out(user)


@router.patch(
    "/users/{id}",
    response_model=UserOut,
    summary="Обновить пользователя",
    description="Обновление профиля/ролей. Только администраторы.",
    responses={403: ERROR_403, 404: ERROR_404},
)
async def update_user(
    id: uuid.UUID,
    payload: UserUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    repo = UserRepository(session)
    user = await repo.get_with_roles(id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    data = payload.model_dump(exclude_unset=True)
    role_codes = data.pop("role_codes", None)
    for k, v in data.items():
        setattr(user, k, v)
    if role_codes is not None:
        await repo.set_roles(user, role_codes)
    await session.flush()
    return _user_out(await repo.get_with_roles(id))


@router.patch(
    "/users/{id}/block",
    response_model=UserOut,
    summary="Заблокировать / разблокировать пользователя",
    description=(
        "Блокировка: обновляет `users.is_blocked` и создаёт запись в `blacklist`; "
        "разблокировка деактивирует активную запись blacklist. "
        "Действие пишется в `audit_log`. Только администраторы."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def block_user(
    id: uuid.UUID,
    payload: BlockRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[object, Depends(require_admin)],
):
    repo = UserRepository(session)
    user = await repo.get_with_roles(id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")

    mod = ModerationRepository(session)
    from datetime import datetime, timezone

    if payload.is_blocked:
        user.is_blocked = True
        user.block_reason = payload.reason
        user.blocked_by = admin.id
        user.blocked_at = datetime.now(timezone.utc)
        await mod.create_blacklist_entry(
            user_id=user.id,
            reason=payload.reason or "Блокировка администратором",
            blocked_by=admin.id,
            expires_at=payload.expires_at,
        )
        action = "block"
    else:
        user.is_blocked = False
        user.block_reason = None
        user.blocked_by = None
        user.blocked_at = None
        await mod.deactivate_blacklist(user.id)
        action = "unblock"
    await session.flush()
    await mod.write_audit(
        user_id=admin.id,
        action=action,
        entity_type="user",
        entity_id=user.id,
        new_values={"is_blocked": payload.is_blocked, "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
    )
    return _user_out(await repo.get_with_roles(id))


# --------------------------------------------------------------- Complaints
@router.post(
    "/complaints",
    response_model=ComplaintOut,
    status_code=status.HTTP_201_CREATED,
    summary="Подать жалобу на пользователя",
    description=(
        "Жалоба сотрудника на пользователя (спам, некорректные обращения). "
        "Статус по умолчанию — `open`. Доступно сотрудникам (support/admin)."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def create_complaint(
    payload: ComplaintCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_current_user)],
):
    actor = make_actor(current, request)
    from app.core.security import is_staff

    if not is_staff(actor.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Жалобы могут подавать только сотрудники")
    urepo = UserRepository(session)
    target = await urepo.get(payload.target_user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Целевой пользователь не найден")

    complaint = Complaint(
        complainant_id=actor.user_id,
        target_user_id=payload.target_user_id,
        ticket_id=payload.ticket_id,
        reason=payload.reason,
    )
    session.add(complaint)
    await session.flush()
    await ModerationRepository(session).write_audit(
        user_id=actor.user_id,
        action="create",
        entity_type="complaint",
        entity_id=complaint.id,
        new_values={"target_user_id": str(payload.target_user_id)},
        ip_address=request.client.host if request.client else None,
    )
    return complaint


@router.get(
    "/complaints",
    response_model=Page[ComplaintOut],
    summary="Список жалоб",
    description="Пагинированный список жалоб с фильтром по статусу. Только администраторы.",
    responses={403: ERROR_403},
)
async def list_complaints(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status", examples=["open"]),
):
    items = await ModerationRepository(session).list_complaints(
        offset=(page - 1) * page_size, limit=page_size, status=status_filter
    )
    return build_page(list(items), len(items), page, page_size, ComplaintOut)
