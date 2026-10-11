"""Репозиторий тикетов: фильтры, пагинация, лимиты по времени, история."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.references import TicketStatus
from app.models.tickets import Ticket, TicketHistory, TicketMessage
from app.repositories.base import BaseRepository


class TicketRepository(BaseRepository[Ticket]):
    model = Ticket

    def _loaded(self):
        return self._base_stmt().options(
            joinedload(Ticket.status),
            joinedload(Ticket.type),
            joinedload(Ticket.priority),
            joinedload(Ticket.source),
            joinedload(Ticket.address),
            joinedload(Ticket.author),
            joinedload(Ticket.assignee),
        )

    async def get_full(self, ticket_id: uuid.UUID) -> Ticket | None:
        result = await self.session.execute(
            self._loaded().where(Ticket.id == ticket_id)
        )
        return result.unique().scalar_one_or_none()

    async def list_filtered(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        status_code: str | None = None,
        address_id: uuid.UUID | None = None,
        assignee_id: uuid.UUID | None = None,
        author_id: uuid.UUID | None = None,
        unassigned_only: bool = False,
    ) -> tuple[Sequence[Ticket], int]:
        stmt = self._loaded()
        count_stmt = (
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.is_deleted == False)  # noqa: E712
        )

        if status_code:
            cond = Ticket.status.has(TicketStatus.code == status_code)
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        if address_id:
            stmt = stmt.where(Ticket.address_id == address_id)
            count_stmt = count_stmt.where(Ticket.address_id == address_id)
        if assignee_id:
            stmt = stmt.where(Ticket.assigned_to == assignee_id)
            count_stmt = count_stmt.where(Ticket.assigned_to == assignee_id)
        if author_id:
            stmt = stmt.where(Ticket.author_id == author_id)
            count_stmt = count_stmt.where(Ticket.author_id == author_id)
        if unassigned_only:
            stmt = stmt.where(Ticket.assigned_to.is_(None))
            count_stmt = count_stmt.where(Ticket.assigned_to.is_(None))

        stmt = stmt.order_by(Ticket.created_at.desc()).offset(offset).limit(limit)
        items = (await self.session.execute(stmt)).unique().scalars().all()
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return items, total

    async def count_recent_by_author(
        self, author_id: uuid.UUID, since: datetime
    ) -> int:
        """Сколько тикетов создал автор за период (для role_limits)."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.author_id == author_id,
                Ticket.is_deleted == False,  # noqa: E712
                Ticket.created_at >= since,
            )
        )
        return int(result.scalar_one())

    async def tickets_per_hour(self, author_id: uuid.UUID) -> int:
        return await self.count_recent_by_author(author_id, datetime.now(timezone.utc) - timedelta(hours=1))

    async def tickets_per_day(self, author_id: uuid.UUID) -> int:
        return await self.count_recent_by_author(author_id, datetime.now(timezone.utc) - timedelta(days=1))

    async def add_history(
        self,
        ticket_id: uuid.UUID,
        changed_by: uuid.UUID,
        field_name: str,
        old_value: str | None,
        new_value: str | None,
    ) -> TicketHistory:
        h = TicketHistory(
            ticket_id=ticket_id,
            changed_by=changed_by,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
        )
        self.session.add(h)
        await self.session.flush()
        return h

    async def list_messages(self, ticket_id: uuid.UUID, include_internal: bool) -> Sequence[TicketMessage]:
        stmt = (
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id, TicketMessage.is_deleted == False)  # noqa: E712
            .options(selectinload(TicketMessage.author))
            .order_by(TicketMessage.created_at.asc())
        )
        if not include_internal:
            stmt = stmt.where(TicketMessage.is_internal == False)  # noqa: E712
        return (await self.session.execute(stmt)).scalars().all()

    async def get_status_by_code(self, code: str) -> TicketStatus | None:
        result = await self.session.execute(
            select(TicketStatus).where(TicketStatus.code == code, TicketStatus.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()
