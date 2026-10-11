"""Эндпоинты интеграции с MAX: вебхуки, отправка сообщений, прокси профиля.

Бот MAX (будущий клиент) использует эти методы как «тонкий» слой к внутренним сервисам API.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.v1.common import ERROR_400, ERROR_403
from app.core.database import get_db
from app.repositories.misc_repos import ModerationRepository
from app.repositories.users_repo import UserRepository
from app.schemas.integrations import (
    MaxProfileResponse,
    MaxSendMessageRequest,
    MaxSendMessageResponse,
    MaxWebhookPayload,
    MaxWebhookResult,
)
from app.services.max_api_service import MaxApiError, MaxApiService

router = APIRouter(prefix="/integrations/max", tags=["Integrations (MAX)"])


async def _upsert_user_from_max(session: AsyncSession, profile: dict) -> tuple[object, bool]:
    """Создать/обновить пользователя по данным профиля MAX. Возвращает (user, created)."""
    repo = UserRepository(session)
    max_id = int(profile.get("user_id") or profile.get("max_user_id"))
    user = await repo.get_by_max_id(max_id)
    fields = {
        "first_name": profile.get("first_name"),
        "name": profile.get("name"),
        "username": profile.get("username"),
        "is_bot": bool(profile.get("is_bot", False)),
        "last_activity_time": profile.get("last_activity_time"),
        "raw_profile": profile,
    }
    if user is None:
        user = await repo.create(max_user_id=max_id, **fields)
        return user, True
    for k, v in fields.items():
        if v is not None:
            setattr(user, k, v)
    await session.flush()
    return user, False


@router.post(
    "/webhooks",
    response_model=MaxWebhookResult,
    summary="Приём событий от MAX",
    description=(
        "Вебхук-приёмник событий MAX (упрощённая схема по dev.max.ru/docs): "
        "`user_created` / `user_updated` создают или обновляют профиль пользователя в БД "
        "(6 полей MAX + сырой JSON в `raw_profile`). События пишутся в `audit_log`. "
        "Метод защищён правами администратора (или сервисным ключом на уровне сети)."
    ),
    responses={400: ERROR_400, 403: ERROR_403},
)
async def max_webhook(
    payload: MaxWebhookPayload,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    if payload.event_type in ("user_created", "user_updated"):
        if not payload.user or not (payload.user.get("user_id") or payload.user.get("max_user_id")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Для события пользователя требуется поле user.user_id")
        user, created = await _upsert_user_from_max(session, payload.user)
        await ModerationRepository(session).write_audit(
            user_id=None,
            action="max_webhook_user" + ("_created" if created else "_updated"),
            entity_type="user",
            entity_id=user.id,
            new_values={"max_user_id": user.max_user_id},
            ip_address=request.client.host if request.client else None,
        )
        return MaxWebhookResult(processed=True, action="user_created" if created else "user_updated", user_db_id=str(user.id))

    # message_created/message_updated/callback — бот обрабатывает сам; фиксируем факт получения
    await ModerationRepository(session).write_audit(
        user_id=None,
        action=f"max_webhook_{payload.event_type}",
        entity_type="max_event",
        new_values=payload.payload or {},
        ip_address=request.client.host if request.client else None,
    )
    return MaxWebhookResult(processed=True, action=payload.event_type)


@router.post(
    "/send-message",
    response_model=MaxSendMessageResponse,
    summary="Отправить сообщение пользователю в MAX",
    description=(
        "Метод для внутренних сервисов и будущего бота: отправляет текст (и опционально "
        "inline-кнопки) через MAX API (`POST /v3/messages?user_id=...`, авторизация "
        "`Access token <BOT_TOKEN>`). Пользователь должен существовать в БД по max_user_id. "
        "Факт отправки пишется в `notifications`/`notification_history` и `audit_log`."
    ),
    responses={400: ERROR_400, 403: ERROR_403},
)
async def send_message(
    payload: MaxSendMessageRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[object, Depends(require_admin)],
):
    from app.models.notifications import Notification, NotificationHistory

    urepo = UserRepository(session)
    user = await urepo.get_by_max_id(payload.max_user_id)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Пользователь с max_user_id={payload.max_user_id} не найден в БД"
        )

    notif = Notification(user_id=user.id, message=payload.text)
    session.add(notif)
    await session.flush()
    hist = NotificationHistory(notification_id=notif.id, status="pending")
    session.add(hist)
    await session.flush()

    try:
        resp = await MaxApiService().send_message(
            payload.max_user_id,
            payload.text,
            buttons=payload.buttons,
            disable_notification=payload.disable_notification,
        )
    except MaxApiError as exc:
        hist.status = "failed"
        hist.error_message = exc.detail[:2000]
        await session.flush()
        return MaxSendMessageResponse(sent=False, detail=str(exc))

    hist.status = "sent"
    from datetime import datetime, timezone

    hist.sent_at = datetime.now(timezone.utc)
    await session.flush()
    await ModerationRepository(session).write_audit(
        user_id=admin.id,
        action="max_send_message",
        entity_type="notification",
        entity_id=notif.id,
        new_values={"max_user_id": payload.max_user_id},
    )
    msg_id = None
    if isinstance(resp, dict):
        msg_id = str(resp.get("message_id") or resp.get("id") or "") or None
    return MaxSendMessageResponse(sent=True, message_id=msg_id)


@router.get(
    "/profile/{max_user_id}",
    response_model=MaxProfileResponse,
    summary="Прокси-запрос профиля из MAX API",
    description=(
        "Возвращает актуальный профиль пользователя напрямую из MAX API "
        "(`GET /v3/users?user_id=...`) и признак наличия пользователя в нашей БД. "
        "Полезен боту для синхронизации данных."
    ),
    responses={403: ERROR_403},
)
async def get_profile(
    max_user_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    found = await UserRepository(session).get_by_max_id(max_user_id) is not None
    try:
        profile = await MaxApiService().get_user(max_user_id)
    except MaxApiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"MAX API недоступен: {exc.detail}")
    return MaxProfileResponse(found_in_db=found, max_user_id=max_user_id, profile=profile)
