"""Сервис геймификации: начисление/списание баллов, лимиты ролей, рейтинг."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import UserPoints
from app.repositories.misc_repos import PointsRepository
from app.repositories.users_repo import UserRepository


class PointsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PointsRepository(session)
        self.users = UserRepository(session)

    async def get_balance(self, user_id: uuid.UUID) -> UserPoints:
        return await self.repo.get_or_create(user_id)

    async def apply_points(
        self,
        *,
        user_id: uuid.UUID,
        amount: int,
        reason: str,
        performed_by: uuid.UUID,
        rule_code: str | None = None,
        ticket_id: uuid.UUID | None = None,
    ):
        """Изменить баланс и записать транзакцию. amount != 0."""
        if amount == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "amount не может быть 0")
        balance = await self.repo.get_for_update(user_id) or await self.repo.get_or_create(user_id)
        balance.balance += amount
        rule = await self.repo.get_rule(rule_code) if rule_code else None
        tx = await self.repo.add_transaction(
            user_id=user_id,
            amount=amount,
            reason=reason,
            performed_by=performed_by,
            rule_id=rule.id if rule else None,
            ticket_id=ticket_id,
        )
        return balance, tx

    async def charge_for_ticket_creation(
        self, *, user_id: uuid.UUID, ticket_number: int, ticket_id: uuid.UUID
    ) -> int | None:
        """Списать баллы за создание тикета по правилу 'ticket_create'.

        Возвращает списанную сумму (отрицательную) или None, если правило не задано.
        Блокирует создание, если баланс уйдёт в минус.
        """
        rule = await self.repo.get_rule("ticket_create")
        if rule is None or rule.amount >= 0:
            return None
        balance = await self.repo.get_or_create(user_id)
        if balance.balance + rule.amount < 0:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"Недостаточно баллов для создания тикета: баланс {balance.balance}, "
                f"требуется {abs(rule.amount)}",
            )
        await self.apply_points(
            user_id=user_id,
            amount=rule.amount,
            reason=f"Списание за создание тикета #{ticket_number}",
            performed_by=user_id,
            rule_code="ticket_create",
            ticket_id=ticket_id,
        )
        return rule.amount

    async def refund_on_close(
        self, *, user_id: uuid.UUID, ticket_number: int, ticket_id: uuid.UUID, performed_by: uuid.UUID
    ) -> int | None:
        """Возврат баллов при закрытии тикета (правило 'ticket_refund', по умолчанию = сумме списания)."""
        rule = await self.repo.get_rule("ticket_refund")
        if rule is None:
            create_rule = await self.repo.get_rule("ticket_create")
            if create_rule is None or create_rule.amount >= 0:
                return None
            amount = abs(create_rule.amount)
        else:
            amount = abs(rule.amount)
        await self.apply_points(
            user_id=user_id,
            amount=amount,
            reason=f"Возврат баллов за закрытие тикета #{ticket_number}",
            performed_by=performed_by,
            rule_code=rule.code if rule else None,
            ticket_id=ticket_id,
        )
        return amount

    async def penalty_for_duplicate(
        self, *, user_id: uuid.UUID, ticket_number: int, ticket_id: uuid.UUID, performed_by: uuid.UUID
    ) -> int | None:
        """Штраф за дубль (правило 'duplicate_penalty')."""
        rule = await self.repo.get_rule("duplicate_penalty")
        if rule is None or rule.amount >= 0:
            return None
        await self.apply_points(
            user_id=user_id,
            amount=rule.amount,
            reason=f"Штраф за дубль тикета #{ticket_number}",
            performed_by=performed_by,
            rule_code="duplicate_penalty",
            ticket_id=ticket_id,
        )
        return rule.amount

    async def check_role_limits(
        self, *, user_id: uuid.UUID, role_codes: set[str]
    ) -> None:
        """Проверка role_limits: min_rating, max_tickets_per_hour/day. Бросает 403/429."""
        from app.models.references import Role
        from sqlalchemy import select

        role_ids = (
            (await self.session.execute(select(Role.id).where(Role.code.in_(role_codes))))
            .scalars()
            .all()
        )
        limit = await self.repo.get_role_limit(set(role_ids))
        if limit is None:
            return
        user = await self.users.get(user_id)
        if limit.min_rating is not None and user and user.rating < limit.min_rating:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Рейтинг {user.rating} ниже минимально допустимого ({limit.min_rating})",
            )
        from app.repositories.tickets_repo import TicketRepository

        trepo = TicketRepository(self.session)
        if limit.max_tickets_per_hour is not None:
            per_hour = await trepo.tickets_per_hour(user_id)
            if per_hour >= limit.max_tickets_per_hour:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Превышен лимит тикетов в час ({limit.max_tickets_per_hour})",
                )
        if limit.max_tickets_per_day is not None:
            per_day = await trepo.tickets_per_day(user_id)
            if per_day >= limit.max_tickets_per_day:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Превышен лимит тикетов в сутки ({limit.max_tickets_per_day})",
                )
