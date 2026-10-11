"""Сервис жизненного цикла тикетов: создание с лимитами, статусы, назначение, дубли, история."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import is_admin, is_staff
from app.models.references import TicketSource
from app.models.tickets import Ticket, TicketHistory, TicketMessage
from app.repositories.misc_repos import ModerationRepository
from app.repositories.tickets_repo import TicketRepository
from app.repositories.users_repo import UserRepository
from app.schemas.tickets import (
    TicketAssign,
    TicketCreate,
    TicketDuplicate,
    TicketStatusChange,
)
from app.services.points_service import PointsService

#: Статусы, которые может ставить не-админ
NON_ADMIN_ALLOWED_STATUSES = {"new", "in_progress", "done", "canceled"}
CLOSED_STATUS_CODES = {"closed", "done"}


class TicketService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TicketRepository(session)
        self.users = UserRepository(session)
        self.points = PointsService(session)
        self.moderation = ModerationRepository(session)

    # ---------- Создание ----------

    async def create_ticket(self, payload: TicketCreate, actor: TicketActor) -> Ticket:
        """Создание тикета: проверка блокировки, лимитов роли, списание баллов."""
        user = await self.users.get_with_roles(actor.user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
        if user.is_blocked:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Пользователь заблокирован")

        role_codes = self.users.role_codes_of(user)
        await self.points.check_role_limits(user_id=user.id, role_codes=role_codes)

        status_new = await self.repo.get_status_by_code("new")
        if status_new is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "В справочнике отсутствует статус 'new' — выполните сидирование",
            )
        source_id = payload.source_id or actor.default_source_id
        if source_id is None:
            # Источник по умолчанию — первый активный (например, 'web')
            from sqlalchemy import select

            default_src = (
                await self.session.execute(
                    select(TicketSource)
                    .where(TicketSource.is_active == True)  # noqa: E712
                    .order_by(TicketSource.code.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if default_src is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Не указан source_id и в справочнике нет активных источников"
                )
            source_id = default_src.id

        ticket = await self.repo.create(
            type_id=payload.type_id,
            status_id=status_new.id,
            priority_id=payload.priority_id,
            source_id=source_id,
            title=payload.title,
            description=payload.description,
            author_id=user.id,
            address_id=payload.address_id or user.default_address_id,
            cabinet=payload.cabinet,
        )
        # История создания + списание баллов
        await self.repo.add_history(ticket.id, user.id, "created", None, f"тикет #{ticket.ticket_number} создан")
        await self.points.charge_for_ticket_creation(
            user_id=user.id, ticket_number=ticket.ticket_number, ticket_id=ticket.id
        )
        await self.moderation.write_audit(
            user_id=user.id,
            action="create",
            entity_type="ticket",
            entity_id=ticket.id,
            new_values={"title": ticket.title, "ticket_number": ticket.ticket_number},
            ip_address=actor.ip,
        )
        return await self.repo.get_full(ticket.id)

    # ---------- Чтение ----------

    async def get_detail(self, ticket_id: uuid.UUID, actor: TicketActor):
        ticket = await self.repo.get_full(ticket_id)
        if ticket is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Тикет не найден")
        messages = await self.repo.list_messages(ticket_id, include_internal=actor.is_staff)
        from sqlalchemy import select

        hist_rows = (
            (
                await self.session.execute(
                    select(TicketHistory)
                    .where(TicketHistory.ticket_id == ticket_id)
                    .order_by(TicketHistory.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        return ticket, list(hist_rows), messages

    # ---------- Назначение ----------

    async def assign(self, ticket_id: uuid.UUID, payload: TicketAssign, actor: TicketActor) -> Ticket:
        ticket = await self.repo.get(ticket_id)
        if ticket is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Тикет не найден")

        executor_id = payload.executor_id or actor.user_id
        if executor_id != actor.user_id and not actor.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Назначить другого исполнителя может только admin")
        if not actor.is_staff:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Брать задачи могут только сотрудники (support/admin)")

        executor = await self.users.get(executor_id)
        if executor is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Исполнитель не найден")

        old_assignee = str(ticket.assigned_to) if ticket.assigned_to else None
        ticket.assigned_to = executor_id
        ticket.assigned_at = _now()
        await self.session.flush()

        await self.repo.add_history(ticket_id, actor.user_id, "assigned_to", old_assignee, str(executor_id))
        # Автопереход в «в работе», если тикет ещё новый
        if ticket.status and ticket.status.code == "new":
            in_progress = await self.repo.get_status_by_code("in_progress")
            if in_progress:
                old_status = ticket.status.code
                ticket.status_id = in_progress.id
                await self.session.flush()
                await self.repo.add_history(ticket_id, actor.user_id, "status_id", old_status, in_progress.code)
                await self._refresh_relations(ticket)

        await self.moderation.write_audit(
            user_id=actor.user_id,
            action="assign",
            entity_type="ticket",
            entity_id=ticket_id,
            old_values={"assigned_to": old_assignee},
            new_values={"assigned_to": str(executor_id)},
            ip_address=actor.ip,
        )
        return await self.repo.get_full(ticket_id)

    # ---------- Статусы ----------

    async def change_status(self, ticket_id: uuid.UUID, payload: TicketStatusChange, actor: TicketActor) -> Ticket:
        ticket = await self.repo.get_full(ticket_id)
        if ticket is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Тикет не найден")

        new_status = await self.repo.get_status_by_code(payload.status_code)
        if new_status is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Статус '{payload.status_code}' не найден")

        # Закрыть/отклонить/пометить дублем может только admin
        restricted = {"closed", "rejected", "duplicate"}
        if new_status.code in restricted and not actor.is_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Устанавливать статус '{new_status.code}' может только admin"
            )
        if not actor.is_admin and new_status.code not in NON_ADMIN_ALLOWED_STATUSES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для смены статуса")

        old_code = ticket.status.code if ticket.status else None
        ticket.status_id = new_status.id
        await self.session.flush()
        await self.repo.add_history(ticket_id, actor.user_id, "status_id", old_code, new_status.code)

        if new_status.code == "closed":
            ticket.closed_by = actor.user_id
            ticket.closed_at = _now()
            await self.session.flush()
            # Возврат баллов автору при закрытии
            await self.points.refund_on_close(
                user_id=ticket.author_id,
                ticket_number=ticket.ticket_number,
                ticket_id=ticket.id,
                performed_by=actor.user_id,
            )
        await self.moderation.write_audit(
            user_id=actor.user_id,
            action="close" if new_status.code == "closed" else "update",
            entity_type="ticket",
            entity_id=ticket_id,
            old_values={"status": old_code},
            new_values={"status": new_status.code},
            ip_address=actor.ip,
        )
        return await self.repo.get_full(ticket_id)

    # ---------- Дубли ----------

    async def mark_duplicate(self, ticket_id: uuid.UUID, payload: TicketDuplicate, actor: TicketActor) -> Ticket:
        if not actor.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Признавать дубль может только admin")
        ticket = await self.repo.get_full(ticket_id)
        if ticket is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Тикет не найден")
        original = await self.repo.get(payload.duplicate_of)
        if original is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Оригинальный тикет не найден")
        if original.id == ticket.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Тикет не может быть дублем самого себя")

        dup_status = await self.repo.get_status_by_code("duplicate")
        if dup_status is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Отсутствует статус 'duplicate'")

        old_status = ticket.status.code if ticket.status else None
        ticket.status_id = dup_status.id
        ticket.duplicate_of = original.id
        await self.session.flush()

        await self.repo.add_history(ticket_id, actor.user_id, "status_id", old_status, "duplicate")
        await self.repo.add_history(ticket_id, actor.user_id, "duplicate_of", None, str(original.id))

        # Штраф за дубль + запись в penalties
        await self.points.penalty_for_duplicate(
            user_id=ticket.author_id,
            ticket_number=ticket.ticket_number,
            ticket_id=ticket.id,
            performed_by=actor.user_id,
        )
        await self.moderation.write_audit(
            user_id=actor.user_id,
            action="duplicate",
            entity_type="ticket",
            entity_id=ticket_id,
            new_values={"duplicate_of": str(original.id)},
            ip_address=actor.ip,
        )
        return await self.repo.get_full(ticket_id)

    # ---------- Сообщения ----------

    async def add_message(self, ticket_id: uuid.UUID, *, message: str, is_internal: bool, actor: TicketActor) -> TicketMessage:
        ticket = await self.repo.get(ticket_id)
        if ticket is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Тикет не найден")
        if is_internal and not actor.is_staff:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Внутренние сообщения доступны только сотрудникам")
        msg = TicketMessage(ticket_id=ticket_id, author_id=actor.user_id, message=message, is_internal=is_internal)
        self.session.add(msg)
        await self.session.flush()
        return msg

    # ---------- Утилиты ----------

    async def _refresh_relations(self, ticket: Ticket) -> None:
        await self.session.refresh(ticket, attribute_names=["status"])


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


class TicketActor:
    """Контекст действия: кто и откуда выполняет операцию."""

    def __init__(
        self,
        user_id: uuid.UUID,
        roles: set[str],
        ip: str | None = None,
        default_source_id: uuid.UUID | None = None,
    ) -> None:
        self.user_id = user_id
        self.roles = roles
        self.ip = ip
        self.default_source_id = default_source_id

    @property
    def is_admin(self) -> bool:
        return is_admin(self.roles)

    @property
    def is_staff(self) -> bool:
        from app.core.security import is_staff

        return is_staff(self.roles)
