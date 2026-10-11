"""Эндпоинты тикетов: создание, список, детали, назначение, статусы, сообщения, дубли."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_service_or_user, make_actor, require_admin
from app.api.v1.common import ERROR_403, ERROR_404, ERROR_429
from app.core.database import get_db
from app.repositories.tickets_repo import TicketRepository
from app.schemas.common import MessageResponse, Page
from app.schemas.tickets import (
    TicketAssign,
    TicketBrief,
    TicketCreate,
    TicketDetail,
    TicketDuplicate,
    TicketMessageCreate,
    TicketStatusChange,
)
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _brief(ticket) -> TicketBrief:
    data = TicketBrief.model_validate(ticket, from_attributes=True)
    data.status_code = ticket.status.code if ticket.status else ""
    data.status_name = ticket.status.name if ticket.status else ""
    data.type_name = ticket.type.name if ticket.type else ""
    data.priority_name = ticket.priority.name if ticket.priority else None
    data.address_name = ticket.address.name if ticket.address else None
    return data


def _detail(ticket, history, messages) -> TicketDetail:
    data = TicketDetail.model_validate(ticket, from_attributes=True)
    data.status_code = ticket.status.code if ticket.status else ""
    data.status_name = ticket.status.name if ticket.status else ""
    data.type_name = ticket.type.name if ticket.type else ""
    data.priority_name = ticket.priority.name if ticket.priority else None
    data.address_name = ticket.address.name if ticket.address else None
    data.source_name = ticket.source.name if ticket.source else None
    data.history = history
    data.messages = messages
    return data


@router.post(
    "",
    response_model=TicketDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Создать тикет",
    description=(
        "Создание обращения. Выполняются проверки:\n\n"
        "* пользователь не заблокирован;\n"
        "* лимиты роли (`role_limits`): max_tickets_per_hour / max_tickets_per_day / min_rating;\n"
        "* списываются баллы по правилу `ticket_create` (при недостатке баланса — 402);\n"
        "* адрес подтягивается из `users.default_address_id`, если не передан;\n"
        "* создаётся запись `ticket_history` и `audit_log`.\n\n"
        "Бот MAX может вызывать эндпоинт по сервисному ключу `X-API-Key` от имени пользователя "
        "(`?user_id=` или `?max_user_id=`)."
    ),
    responses={403: ERROR_403, 429: ERROR_429},
)
async def create_ticket(
    payload: TicketCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_service_or_user)],
):
    actor = make_actor(current, request)
    ticket = await TicketService(session).create_ticket(payload, actor)
    return _detail(ticket, [], [])


@router.get(
    "",
    response_model=Page[TicketBrief],
    summary="Список тикетов",
    description=(
        "Пагинированный список с фильтрами: статус (code), адрес, исполнитель, автор. "
        "Внешним клиентам отдаётся человекочитаемый `ticket_number`; для операций внутри API используется `id` (UUID)."
    ),
    responses={403: ERROR_403},
)
async def list_tickets(
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_service_or_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_code: str | None = Query(None, examples=["new"]),
    address_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    author_id: uuid.UUID | None = None,
    unassigned_only: bool = False,
):
    # Студент (не сотрудник) видит только свои тикеты
    from app.core.security import is_staff

    if not is_staff(_roles(current)):
        author_id = current.id
    items, total = await TicketRepository(session).list_filtered(
        offset=(page - 1) * page_size,
        limit=page_size,
        status_code=status_code,
        address_id=address_id,
        assignee_id=assignee_id,
        author_id=author_id,
        unassigned_only=unassigned_only,
    )
    return {
        "items": [_brief(t) for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


def _roles(user) -> set[str]:
    from app.repositories.users_repo import UserRepository

    return UserRepository.role_codes_of(user)


@router.get(
    "/{id}",
    response_model=TicketDetail,
    summary="Детали тикета",
    description=(
        "Полная карточка тикета с историей изменений, перепиской и вложениями. "
        "Внутренние сообщения (`is_internal=true`) видят только сотрудники. "
        "Студент-неавтор получает 403."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def get_ticket(
    id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_service_or_user)],
):
    actor = make_actor(current, request)
    svc = TicketService(session)
    ticket, history, messages = await svc.get_detail(id, actor)
    if not actor.is_staff and ticket.author_id != actor.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Тикет виден только автору и сотрудникам")
    return _detail(ticket, history, messages)


@router.patch(
    "/{id}/assign",
    response_model=TicketDetail,
    summary="Назначить исполнителя",
    description=(
        "Сотрудник берёт задачу на себя (`executor_id` не передаётся), либо админ назначает другого. "
        "Фиксируется в `ticket_history`; при статусе `new` тикет автоматически переходит в `in_progress`."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def assign_ticket(
    id: uuid.UUID,
    payload: TicketAssign,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_service_or_user)],
):
    actor = make_actor(current, request)
    ticket = await TicketService(session).assign(id, payload, actor)
    return _detail(ticket, [], [])


@router.patch(
    "/{id}/status",
    response_model=TicketDetail,
    summary="Сменить статус тикета",
    description=(
        "Смена статуса с проверкой прав: **закрыть (`closed`), отклонить (`rejected`) или пометить "
        "`duplicate` может только admin**. При закрытии проставляются closed_by/closed_at и "
        "автоматически возвращается баланс баллов автору. Все переходы пишутся в `ticket_history` и `audit_log`."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def change_status(
    id: uuid.UUID,
    payload: TicketStatusChange,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_service_or_user)],
):
    actor = make_actor(current, request)
    ticket = await TicketService(session).change_status(id, payload, actor)
    return _detail(ticket, [], [])


@router.post(
    "/{id}/messages",
    response_model=MessageResponse,
    summary="Добавить сообщение в тикет",
    description=(
        "Сообщение в переписку тикета. Флаг `is_internal=true` разрешён только сотрудникам — "
        "такое сообщение скрыто от заявителя."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def add_message(
    id: uuid.UUID,
    payload: TicketMessageCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(get_service_or_user)],
):
    actor = make_actor(current, request)
    msg = await TicketService(session).add_message(
        id, message=payload.message, is_internal=payload.is_internal, actor=actor
    )
    return MessageResponse(message=f"Сообщение #{msg.id} добавлено")


@router.post(
    "/{id}/duplicate",
    response_model=TicketDetail,
    summary="Признать тикет дублем",
    description=(
        "Только admin. Устанавливает статус `duplicate`, заполняет `duplicate_of`, "
        "начисляет штраф автору по правилу `duplicate_penalty`, пишет историю и аудит."
    ),
    responses={403: ERROR_403, 404: ERROR_404},
)
async def mark_duplicate(
    id: uuid.UUID,
    payload: TicketDuplicate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[object, Depends(require_admin)],
):
    actor = make_actor(current, request)
    ticket = await TicketService(session).mark_duplicate(id, payload, actor)
    return _detail(ticket, [], [])


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить тикет (soft-delete)",
    description="Мягкое удаление тикета. Только администраторы.",
    responses={403: ERROR_403, 404: ERROR_404},
)
async def delete_ticket(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    ok = await TicketRepository(session).soft_delete(id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тикет не найден")
