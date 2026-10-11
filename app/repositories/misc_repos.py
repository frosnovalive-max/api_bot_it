"""Репозитории геймификации (баллы, рейтинг) и модерации (blacklist, жалобы, аудит)."""
import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.gamification import PointRule, PointTransaction, RoleLimit, UserPoints
from app.models.moderation import AuditLog, BlacklistEntry, Complaint, WebAccount
from app.models.users import User, UserRole
from app.repositories.base import BaseRepository


class PointsRepository(BaseRepository[UserPoints]):
    model = UserPoints

    async def get_for_update(self, user_id: uuid.UUID) -> UserPoints | None:
        result = await self.session.execute(
            select(UserPoints)
            .where(UserPoints.user_id == user_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: uuid.UUID) -> UserPoints:
        stmt = select(UserPoints).where(UserPoints.user_id == user_id)
        up = (await self.session.execute(stmt)).scalar_one_or_none()
        if up is None:
            up = UserPoints(user_id=user_id, balance=0)
            self.session.add(up)
            await self.session.flush()
        return up

    async def add_transaction(
        self,
        *,
        user_id: uuid.UUID,
        amount: int,
        reason: str,
        performed_by: uuid.UUID,
        rule_id: uuid.UUID | None = None,
        ticket_id: uuid.UUID | None = None,
    ) -> PointTransaction:
        tx = PointTransaction(
            user_id=user_id,
            rule_id=rule_id,
            ticket_id=ticket_id,
            amount=amount,
            reason=reason[:500],
            performed_by=performed_by,
        )
        self.session.add(tx)
        await self.session.flush()
        return tx

    async def list_transactions(
        self, user_id: uuid.UUID, *, offset: int = 0, limit: int = 50
    ) -> tuple[Sequence[PointTransaction], int]:
        base = select(PointTransaction).where(PointTransaction.user_id == user_id)
        total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(base.subquery())
                )
            ).scalar_one()
        )
        items = (
            (await self.session.execute(base.order_by(PointTransaction.created_at.desc()).offset(offset).limit(limit)))
            .scalars()
            .all()
        )
        return items, total

    async def get_rule(self, code: str) -> PointRule | None:
        result = await self.session.execute(
            select(PointRule).where(PointRule.code == code, PointRule.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def get_role_limit(self, role_ids: set[uuid.UUID]) -> RoleLimit | None:
        """Самое строгое ограничение среди ролей пользователя."""
        if not role_ids:
            return None
        result = await self.session.execute(
            select(RoleLimit).where(
                RoleLimit.role_id.in_(role_ids), RoleLimit.is_active == True  # noqa: E712
            )
        )
        limits = result.scalars().all()
        if not limits:
            return None
        return min(limits, key=lambda l: (l.max_tickets_per_hour or 10**9))

    async def top_rating(self, limit: int = 20) -> Sequence[tuple[User, int]]:
        """Топ по сумме: баланс баллов + рейтинг."""
        stmt = (
            select(User, func.coalesce(UserPoints.balance, 0).label("balance"))
            .outerjoin(UserPoints, UserPoints.user_id == User.id)
            .where(User.is_deleted == False, User.is_active == True)  # noqa: E712,E712
            .order_by((func.coalesce(UserPoints.balance, 0) + User.rating).desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(r[0], r[1]) for r in rows]


class WebAccountRepository(BaseRepository[WebAccount]):
    model = WebAccount

    async def get_by_login(self, login: str) -> WebAccount | None:
        stmt = (
            self._base_stmt()
            .where(WebAccount.login == login, WebAccount.is_active == True)  # noqa: E712
            .options(joinedload(WebAccount.user))
        )
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()


class ModerationRepository(BaseRepository[Complaint]):
    model = Complaint

    async def create_blacklist_entry(
        self,
        *,
        user_id: uuid.UUID,
        reason: str,
        blocked_by: uuid.UUID,
        expires_at=None,
    ) -> BlacklistEntry:
        entry = BlacklistEntry(
            user_id=user_id, reason=reason, blocked_by=blocked_by, expires_at=expires_at
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def deactivate_blacklist(self, user_id: uuid.UUID) -> int:
        from sqlalchemy import update

        result = await self.session.execute(
            update(BlacklistEntry)
            .where(BlacklistEntry.user_id == user_id, BlacklistEntry.is_active == True)  # noqa: E712
            .values(is_active=False)
        )
        return result.rowcount

    async def write_audit(
        self,
        *,
        user_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        old_values: dict | None = None,
        new_values: dict | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_complaints(self, *, offset: int = 0, limit: int = 50, status: str | None = None):
        stmt = self._base_stmt()
        if status:
            stmt = stmt.where(Complaint.status == status)
        stmt = stmt.order_by(Complaint.created_at.desc()).offset(offset).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()
