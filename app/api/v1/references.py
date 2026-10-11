"""Эндпоинты справочников: addresses, ticket_types, ticket_statuses, ticket_priorities, roles, departments.

GET — доступны всем аутентифицированным; CRUD-мутации — только админам (п.5.4 ТЗ).
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.api.v1.common import ERROR_403, ERROR_404, ERROR_409, build_page
from app.core.database import get_db
from app.repositories.base import BaseRepository
from app.schemas.common import Page
from app.schemas.references import (
    AddressCreate,
    AddressOut,
    AddressUpdate,
    PriorityOut,
    RefCreate,
    RefOut,
    RefUpdate,
    RoleCreate,
    RoleOut,
    RoleUpdate,
)
from app.models.references import (
    Address,
    Department,
    Role,
    TicketPriority,
    TicketSource,
    TicketStatus,
    TicketType,
)

router = APIRouter(prefix="/references", tags=["References"])


def _repo(model) -> type[BaseRepository]:
    class _R(BaseRepository):
        pass

    _R.model = model
    return _R


async def _get_or_404(session: AsyncSession, model, obj_id: uuid.UUID):
    repo = _repo(model)(session)
    obj = await repo.get(obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись справочника не найдена")
    return obj


# ------------------------------------------------------------------ Addresses
@router.get(
    "/addresses",
    response_model=Page[AddressOut],
    summary="Список адресов (корпусов)",
    description="Возвращает активные адреса колледжа с пагинацией. Доступен всем аутентифицированным пользователям.",
    responses={403: ERROR_403},
)
async def list_addresses(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = await _repo(Address)(session).list(offset=(page - 1) * page_size, limit=page_size)
    return build_page(list(items), total, page, page_size, AddressOut)


@router.post(
    "/addresses",
    response_model=AddressOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать адрес",
    description="Добавить корпус/адрес. Только для администраторов.",
    responses={403: ERROR_403},
)
async def create_address(
    payload: AddressCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    return await _repo(Address)(session).create(**payload.model_dump())


@router.patch(
    "/addresses/{id}",
    response_model=AddressOut,
    summary="Обновить адрес",
    description="Частичное обновление адреса. Только для администраторов.",
    responses={403: ERROR_403, 404: ERROR_404},
)
async def update_address(
    id: uuid.UUID,
    payload: AddressUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    obj = await _repo(Address)(session).update(id, **payload.model_dump(exclude_unset=True))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    return obj


@router.delete(
    "/addresses/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить адрес (soft-delete)",
    description="Мягкое удаление: is_deleted=true, deleted_at=now(). Записи тикетов сохраняются.",
    responses={403: ERROR_403, 404: ERROR_404},
)
async def delete_address(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    ok = await _repo(Address)(session).soft_delete(id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")


# ------------------------------------------------------------- generic refs
async def _generic_list(session, model, out_cls, page, page_size):
    items, total = await _repo(model)(session).list(offset=(page - 1) * page_size, limit=page_size, order_by="code", desc=False)
    return build_page(list(items), total, page, page_size, out_cls)


async def _generic_create(session, model, payload, table_name):
    repo = _repo(model)(session)
    existing = await repo.get_by(code=payload.code)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Код '{payload.code}' уже существует в {table_name}")
    return await repo.create(**payload.model_dump())


@router.get("/ticket-types", response_model=Page[RefOut], summary="Типы обращений",
            description="Справочник типов тикетов: поломка, запрос доступа, картридж, оборудование.")
async def list_ticket_types(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_current_user)],
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    return await _generic_list(session, TicketType, RefOut, page, page_size)


@router.post("/ticket-types", response_model=RefOut, status_code=201, summary="Создать тип обращения",
            description="Только администраторы.", responses={403: ERROR_403, 409: ERROR_409})
async def create_ticket_type(
    payload: RefCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    return await _generic_create(session, TicketType, payload, "ticket_types")


@router.patch("/ticket-types/{id}", response_model=RefOut, summary="Обновить тип обращения",
              description="Только администраторы.", responses={403: ERROR_403, 404: ERROR_404})
async def update_ticket_type(
    id: uuid.UUID, payload: RefUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    obj = await _repo(TicketType)(session).update(id, **payload.model_dump(exclude_unset=True))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Не найдено")
    return obj


@router.delete("/ticket-types/{id}", status_code=204, summary="Деактивировать тип обращения",
               description="Только администраторы.", responses={403: ERROR_403, 404: ERROR_404})
async def delete_ticket_type(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    obj = await _repo(TicketType)(session).update(id, is_active=False)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Не найдено")


@router.get("/ticket-statuses", response_model=Page[RefOut], summary="Статусы тикетов",
            description="Справочник статусов: new, in_progress, done, closed, rejected, canceled, duplicate.")
async def list_ticket_statuses(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_current_user)],
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    return await _generic_list(session, TicketStatus, RefOut, page, page_size)


@router.post("/ticket-statuses", response_model=RefOut, status_code=201, summary="Создать статус",
             description="Только администраторы.", responses={403: ERROR_403, 409: ERROR_409})
async def create_ticket_status(
    payload: RefCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    return await _generic_create(session, TicketStatus, payload, "ticket_statuses")


@router.patch("/ticket-statuses/{id}", response_model=RefOut, summary="Обновить статус",
              description="Только администраторы.", responses={403: ERROR_403, 404: ERROR_404})
async def update_ticket_status(
    id: uuid.UUID, payload: RefUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    obj = await _repo(TicketStatus)(session).update(id, **payload.model_dump(exclude_unset=True))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Не найдено")
    return obj


@router.delete("/ticket-statuses/{id}", status_code=204, summary="Деактивировать статус",
               description="Только администраторы.", responses={403: ERROR_403, 404: ERROR_404})
async def delete_ticket_status(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    obj = await _repo(TicketStatus)(session).update(id, is_active=False)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Не найдено")


@router.get("/ticket-priorities", response_model=Page[PriorityOut], summary="Приоритеты",
            description="Справочник приоритетов с весом сортировки.")
async def list_priorities(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_current_user)],
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    return await _generic_list(session, TicketPriority, PriorityOut, page, page_size)


@router.get("/ticket-sources", response_model=Page[RefOut], summary="Источники обращений",
            description="Справочник источников: bot, web, personal.")
async def list_sources(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_current_user)],
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    return await _generic_list(session, TicketSource, RefOut, page, page_size)


@router.get("/roles", response_model=Page[RoleOut], summary="Роли",
            description="Справочник ролей: admin, support, teacher, staff, student.")
async def list_roles(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(get_current_user)],
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    return await _generic_list(session, Role, RoleOut, page, page_size)


@router.post("/roles", response_model=RoleOut, status_code=201, summary="Создать роль",
             description="Только администраторы.", responses={403: ERROR_403, 409: ERROR_409})
async def create_role(
    payload: RoleCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    repo = _repo(Role)(session)
    if await repo.get_by(code=payload.code):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Роль '{payload.code}' уже существует")
    return await repo.create(**payload.model_dump())


@router.patch("/roles/{id}", response_model=RoleOut, summary="Обновить роль",
              description="Только администраторы.", responses={403: ERROR_403, 404: ERROR_404})
async def update_role(
    id: uuid.UUID, payload: RoleUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    obj = await _repo(Role)(session).update(id, **payload.model_dump(exclude_unset=True))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Роль не найдена")
    return obj


@router.delete("/roles/{id}", status_code=204, summary="Деактивировать роль",
               description="Мягкая деактивация роли. Только администраторы.",
               responses={403: ERROR_403, 404: ERROR_404})
async def delete_role(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[object, Depends(require_admin)],
):
    obj = await _repo(Role)(session).update(id, is_active=False)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Роль не найдена")
