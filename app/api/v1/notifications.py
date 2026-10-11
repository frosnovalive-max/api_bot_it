"""Эндпоинты очереди уведомлений (паттерн «Очереди в БД»).

Core API формирует уведомления при бизнес-событиях; этот роутер позволяет:
 * пользователю/веб-панели — читать свои уведомления и отмечать прочитанным;
 * Боту/воркеру (сервисный X-API-Key) — выбирать pending-очередь для доставки
   в MAX и отчитываться об итоге (sent/failed).
Сам Core API во внешние сети не ходит.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_service_or_user
from app.api.v1.common import ERROR_403, ERROR_404, build_page
from app.core.database import get_db
from app.repositories.notifications_repo import NotificationsRepository
from app.schemas.common import Page
from app.schemas.notifications import DeliveryStatusUpdate, NotificationOut
from app.schemas.users import UserOut

router = APIRouter(prefix="/notifications", tags=["Notifications Queue"])


def _out(n) -> NotificationOut:
    data = NotificationOut.model_validate(n, from_attributes=True)
    if n.template is not None:
        data.template_code = n.template.code
    return data


@router.get(
    "",
    response_model=Page[NotificationOut],
    summary="Мои уведомления",
    description=(
        "Список уведомлений текущего пользователя (JWT) с пагинацией. "
        "Параметр `only_unread=true` — только непрочитанные."
    ),
    responses={401: ERROR_403},
)
async def my_notifications(
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    only_unread: bool = Query(False),
):
    rows, total = await NotificationsRepository(session).list_for_user(
        current.id, offset=(page - 1) * page_size, limit=page_size, only_unread=only_unread
    )
    return build_page([_out(r) for r in rows], total, page, page_size)


@router.get(
    "/unread-count",
    summary="Количество непрочитанных",
    description="Быстрый счётчик непрочитанных уведомлений текущего пользователя для бейджа в UI.",
)
async def unread_count(
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_current_user)],
):
    count = await NotificationsRepository(session).unread_count(current.id)
    return {"unread": count}


@router.patch(
    "/{id}/read",
    response_model=NotificationOut,
    summary="Отметить уведомление прочитанным",
    description="Пользователь отмечает своё уведомление как прочитанное (`is_read = TRUE`).",
    responses={404: ERROR_404},
)
async def mark_read(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_current_user)],
):
    notif = await NotificationsRepository(session).mark_read(id, current.id)
    if notif is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")
    return _out(notif)


# --------------------------------------------------------------- Для бота ---
@router.get(
    "/queue/pending",
    response_model=list[NotificationOut],
    summary="[Бот] Выбрать недоставленные уведомления",
    description=(
        "Интерфейс воркера доставки: возвращает уведомления со статусом `pending` в "
        "`notification_history`. Бот MAX забирает очередь по сервисному ключу `X-API-Key`, "
        "отправляет текст получателю через MAX API и отчитывается эндпоинтом "
        "`PATCH /notifications/{id}/delivery-status`. Core API сам не общается с MAX."
    ),
    responses={403: ERROR_403},
)
async def pending_queue(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_service_or_user)],
    limit: int = Query(100, ge=1, le=500),
):
    rows = await NotificationsRepository(session).get_pending(limit=limit)
    return [_out(r) for r in rows]


@router.patch(
    "/{id}/delivery-status",
    summary="[Бот] Отчёт о доставке уведомления",
    description=(
        "Бот/воркер обновляет последнюю запись `notification_history`: "
        "`sent` (сообщение доставлено в MAX) или `failed` (с текстом ошибки)."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def update_delivery_status(
    id: uuid.UUID,
    payload: DeliveryStatusUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_service_or_user)],
):
    hist = await NotificationsRepository(session).update_delivery_status(
        id, status=payload.status, error_message=payload.error_message
    )
    if hist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")
    return {"notification_id": str(id), "status": hist.status}
